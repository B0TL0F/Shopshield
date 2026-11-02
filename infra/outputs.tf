output "resource_group" {
  value = azurerm_resource_group.lab.name
}
output "cluster_name" {
  value = azurerm_kubernetes_cluster.lab.name
}
output "deploy_client_id" {
  value = azurerm_user_assigned_identity.deploy.client_id
}
output "deploy_identity_name" {
  value = azurerm_user_assigned_identity.deploy.name
}
