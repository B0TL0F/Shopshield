resource "azurerm_resource_group" "state" {
  name     = "rg-shopshield-tfstate"
  location = var.location
  tags     = { project = "shopshield", purpose = "terraform-state" }
}
