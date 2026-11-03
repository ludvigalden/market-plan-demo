# One-time bootstrap: the Terraform state account, the application resource
# group, and the CD identity that GitHub Actions assumes over OpenID Connect.
# Applied locally by the repository owner, then migrated to its own remote
# state.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.12"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.10"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.13"
    }
  }

  # The state resource group and account names are passed on the command
  # line with -backend-config, so the same file drives every run.
  backend "azurerm" {
    use_azuread_auth = true
    container_name   = "tfstate"
    key              = "bootstrap.tfstate"
  }
}

provider "azurerm" {
  features {}

  resource_providers_to_register = [
    "Microsoft.App",
    "Microsoft.CognitiveServices",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
    "Microsoft.Storage",
  ]
}

locals {
  location      = "swedencentral"
  state_account = "${replace(var.prefix, "-", "")}tfstate"
  oidc_issuer   = "https://token.actions.githubusercontent.com"
  github_owner  = split("/", var.github_repository)[0]
  github_name   = split("/", var.github_repository)[1]
}

data "azuread_client_config" "current" {}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "state" {
  name     = "${var.prefix}-tfstate"
  location = local.location
}

# The main root adopts this group by data source and owns everything in it;
# creating it here lets the CD grants be scoped to it.
resource "azurerm_resource_group" "app" {
  name     = "${var.prefix}-rg"
  location = local.location
}

resource "azurerm_storage_account" "state" {
  name                            = local.state_account
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
}

# Created through the management API because the account rejects shared-key
# access, which the data-plane container resource would need.
resource "azapi_resource" "state_container" {
  type      = "Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01"
  name      = "tfstate"
  parent_id = "${azurerm_storage_account.state.id}/blobServices/default"
}

# The owner applies and reads Terraform state locally. Backend
# initialization lists blobs at container level, so the grant is scoped to
# the container.
resource "azurerm_role_assignment" "owner_state_blob" {
  scope                = "${azurerm_storage_account.state.id}/blobServices/default/containers/tfstate"
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azuread_client_config.current.object_id
}

resource "azuread_application" "cd" {
  display_name     = "${var.prefix}-cd"
  sign_in_audience = "AzureADMyOrg"
}

resource "azuread_service_principal" "cd" {
  client_id       = azuread_application.cd.client_id
  account_enabled = true
}

resource "azuread_application_federated_identity_credential" "cd" {
  application_id = azuread_application.cd.id
  display_name   = "github-actions-production"
  description    = "GitHub Actions deploys from the production environment of ${var.github_repository}."
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = local.oidc_issuer
  subject        = "repo:${var.github_repository}:environment:production"
}

# GitHub's environment-scoped OIDC subjects also carry the immutable owner
# and repository IDs alongside the names; both forms are trusted.
resource "azuread_application_federated_identity_credential" "cd_ids" {
  application_id = azuread_application.cd.id
  display_name   = "github-actions-production-ids"
  description    = "The numeric subject form GitHub puts on environment-scoped tokens for ${var.github_repository}."
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = local.oidc_issuer
  subject        = "repo:${local.github_owner}@${var.github_owner_id}/${local.github_name}@${var.github_repository_id}:environment:production"
}

# Deploys only replace the container app's image; Terraform itself runs
# from the owner's machine, so CD needs no broader grant.
resource "azurerm_role_assignment" "cd_container_apps" {
  scope                = azurerm_resource_group.app.id
  role_definition_name = "Container Apps Contributor"
  principal_id         = azuread_service_principal.cd.object_id
}
