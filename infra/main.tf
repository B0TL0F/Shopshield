resource "azurerm_resource_group" "lab" {
  name     = "rg-${var.name}"
  location = var.location
  tags     = { project = var.name, purpose = "learning" }
}
