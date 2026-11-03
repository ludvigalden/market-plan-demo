# Custom domain with a free managed certificate, in three steps: the
# domain registers on the container app, the certificate issues once DNS
# validates it, and the certificate binds to the domain. Everything stays
# at count zero while the hostname is empty, so provisioning never waits
# on DNS.
#
# A managed certificate needs its domain to exist first, and the domain
# cannot name a certificate that does not exist yet. The azurerm pair
# therefore registers the domain unbound and issues the certificate; an
# ARM PATCH then attaches the certificate with SNI. It is a real merge
# PATCH rather than azapi_update_resource, whose read-modify-PUT sends the
# app's secrets back without their values and is rejected.

locals {
  bind_domain = var.public_hostname != "" ? 1 : 0
}

resource "azurerm_container_app_custom_domain" "public" {
  count = local.bind_domain

  name             = var.public_hostname
  container_app_id = azurerm_container_app.app.id

  lifecycle {
    # The PATCH below owns the binding; without this the provider would
    # reset it to Disabled on every apply.
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }
}

resource "azurerm_container_app_environment_managed_certificate" "public" {
  count = local.bind_domain

  name                         = "${var.prefix}-cert"
  container_app_environment_id = azurerm_container_app_environment.env.id
  subject_name                 = var.public_hostname
  domain_control_validation    = "CNAME"

  depends_on = [azurerm_container_app_custom_domain.public]
}

resource "azapi_resource_action" "domain_binding" {
  count = local.bind_domain

  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = azurerm_container_app.app.id
  method      = "PATCH"

  body = {
    properties = {
      configuration = {
        ingress = {
          customDomains = [
            {
              name          = var.public_hostname
              bindingType   = "SniEnabled"
              certificateId = azurerm_container_app_environment_managed_certificate.public[0].id
            }
          ]
        }
      }
    }
  }

  depends_on = [azurerm_container_app_environment_managed_certificate.public]
}
