data "azurerm_resource_group" "app" {
  name = "${var.prefix}-rg"
}

locals {
  location            = data.azurerm_resource_group.app.location
  ai_subdomain        = "${var.prefix}-ai"
  database_url_secret = "postgresql+asyncpg://plandesk:${random_password.postgres.result}@${azurerm_postgresql_flexible_server.server.fqdn}:5432/${azurerm_postgresql_flexible_server_database.database.name}?ssl=require"
}

# The workload identity of the running app: pulls the image and holds the
# data-plane role for Foundry inference.
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.prefix}-app-id"
  resource_group_name = data.azurerm_resource_group.app.name
  location            = local.location
}

# Short-lived logs for a demo: lowest retention, a daily cap that stops an
# accidental log loop from costing anything.
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${var.prefix}-logs"
  resource_group_name = data.azurerm_resource_group.app.name
  location            = local.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.1
}

resource "azurerm_container_app_environment" "env" {
  name                       = "${var.prefix}-env"
  resource_group_name        = data.azurerm_resource_group.app.name
  location                   = local.location
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id

  # The service provisions this profile by default; declaring it keeps the
  # next plan free of drift.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# Private image registry. The container app pulls with its managed identity
# and no registry password exists anywhere.
resource "azurerm_container_registry" "acr" {
  name                = "${replace(var.prefix, "-", "")}acr"
  resource_group_name = data.azurerm_resource_group.app.name
  location            = local.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_role_assignment" "app_acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Smallest server that works: one burstable vCore, the minimum storage.
# Sweden Central refuses the burstable SKU at create time on this
# subscription, so the server sits in the nearest region that accepts it.
# Password authentication stays on; the password exists only in Terraform
# state and the container app secret, generated and never committed.
resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "server" {
  name                   = "${var.prefix}-pg-${var.postgres_location_short}"
  resource_group_name    = data.azurerm_resource_group.app.name
  location               = var.postgres_location
  version                = var.postgres_version
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  backup_retention_days  = 7
  administrator_login    = "plandesk"
  administrator_password = random_password.postgres.result

  authentication {
    password_auth_enabled = true
  }

  lifecycle {
    # The service picks the zone; pinning it would force a replacement.
    ignore_changes = [zone]
  }
}

# Container Apps egress does not come from fixed addresses; Azure-internal
# access is allowed and the server has no other public surface in use.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.server.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "database" {
  name      = "plandesk"
  server_id = azurerm_postgresql_flexible_server.server.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Microsoft Foundry: the AIServices account carries the model deployment,
# the project gives the app an OpenAI-compatible endpoint for it.
resource "azurerm_cognitive_account" "ai" {
  name                       = "${var.prefix}-ai"
  resource_group_name        = data.azurerm_resource_group.app.name
  location                   = local.location
  kind                       = "AIServices"
  sku_name                   = "S0"
  custom_subdomain_name      = local.ai_subdomain
  local_auth_enabled         = false
  project_management_enabled = true

  # Foundry project management requires the account to hold an identity.
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_account_project" "project" {
  cognitive_account_id = azurerm_cognitive_account.ai.id
  location             = local.location
  name                 = "${var.prefix}-project"
  display_name         = "Market Plan Desk"
  description          = "Localisation suggestions for marketing campaign plans."

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.chat_model_deployment_name
  cognitive_account_id = azurerm_cognitive_account.ai.id
  rai_policy_name      = "Microsoft.DefaultV2"

  model {
    format  = "OpenAI"
    name    = "gpt-4.1-mini"
    version = "2025-04-14"
  }

  sku {
    # The EU data zone rather than regional Standard: the subscription's
    # regional Standard quota for this model is nearly exhausted by another
    # project, and residency is unchanged for a Sweden deployment.
    name     = "DataZoneStandard"
    capacity = 20
  }
}

# Inference over Entra ID only: the app identity for the running app, the
# CD identity for the deploy-time eval, the owner for local runs.
resource "azurerm_role_assignment" "ai_user_app" {
  scope                = azurerm_cognitive_account.ai.id
  role_definition_name = "Foundry User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "ai_user_cd" {
  scope                = azurerm_cognitive_account.ai.id
  role_definition_name = "Foundry User"
  principal_id         = var.cd_principal_object_id
}

resource "azurerm_role_assignment" "ai_user_owner" {
  count = var.owner_principal_object_id == "" ? 0 : 1

  scope                = azurerm_cognitive_account.ai.id
  role_definition_name = "Foundry User"
  principal_id         = var.owner_principal_object_id
}

# The deploy workflow pushes the image it then rolls out.
resource "azurerm_role_assignment" "cd_acr_push" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPush"
  principal_id         = var.cd_principal_object_id
}

# az acr login resolves the registry through the management API, which
# AcrPush alone does not allow.
resource "azurerm_role_assignment" "cd_acr_reader" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "Reader"
  principal_id         = var.cd_principal_object_id
}
