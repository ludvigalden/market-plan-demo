output "app_url" {
  description = "Public URL of the deployed app."
  value       = "https://${azurerm_container_app.app.latest_revision_fqdn}"
}

output "stable_app_url" {
  description = "Stable hostname of the app (revision-independent)."
  value       = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}

output "container_app_name" {
  value = azurerm_container_app.app.name
}

output "resource_group_name" {
  value = data.azurerm_resource_group.app.name
}

output "registry_login_server" {
  value = azurerm_container_registry.acr.login_server
}

output "foundry_project_endpoint" {
  description = "FOUNDRY_PROJECT_ENDPOINT for the app and the eval."
  value       = azurerm_cognitive_account_project.project.endpoints["AI Foundry API"]
}

output "foundry_model_deployment" {
  value = var.chat_model_deployment_name
}

output "app_identity_client_id" {
  value = azurerm_user_assigned_identity.app.client_id
}
