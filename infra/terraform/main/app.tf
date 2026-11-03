# One container serves the SPA and the API. Consumption plan, scaled to
# zero when idle; migrations run in the container entrypoint before the
# server binds, so a revision starts serving only on a migrated schema.
resource "azurerm_container_app" "app" {
  name                         = "${var.prefix}-app"
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = data.azurerm_resource_group.app.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "plandesk"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      # DefaultAzureCredential picks the workload identity up through this
      # well-known variable.
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }
      env {
        name  = "AI_PROVIDER"
        value = "foundry"
      }
      env {
        name  = "FOUNDRY_PROJECT_ENDPOINT"
        value = azurerm_cognitive_account_project.project.endpoints["AI Foundry API"]
      }
      env {
        name  = "FOUNDRY_MODEL_DEPLOYMENT"
        value = var.chat_model_deployment_name
      }

      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/healthz"
        initial_delay           = 10
        interval_seconds        = 5
        timeout                 = 3
        failure_count_threshold = 10
      }
    }
  }

  secret {
    name  = "database-url"
    value = local.database_url_secret
  }

  ingress {
    target_port      = 8000
    external_enabled = true
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  lifecycle {
    # Deploys replace the image; Terraform owns the shape around it.
    ignore_changes = [template[0].container[0].image]
  }
}
