resource "azurerm_user_assigned_identity" "aks" {
  name                = "id-${var.name}-controlplane"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
}

resource "azurerm_user_assigned_identity" "deploy" {
  name                = "id-${var.name}-github"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
}
