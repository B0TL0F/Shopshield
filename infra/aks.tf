resource "azurerm_kubernetes_cluster" "lab" {
  name                              = "aks-${var.name}"
  location                          = azurerm_resource_group.lab.location
  resource_group_name               = azurerm_resource_group.lab.name
  dns_prefix                        = var.name
  sku_tier                          = "Free"
  local_account_disabled            = true
  role_based_access_control_enabled = true
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true
  azure_active_directory_role_based_access_control {
    azure_rbac_enabled     = true
    admin_group_object_ids = [var.admin_group_id]
  }
  api_server_access_profile {
    authorized_ip_ranges = var.api_allowed_cidrs
  }
  default_node_pool {
    name            = "system"
    node_count      = 1 # Central India lab quota constraint.
    vm_size         = var.vm_size
    vnet_subnet_id  = azurerm_subnet.aks.id
    max_pods        = 30
    os_disk_size_gb = 64
    os_disk_type    = "Managed"
    upgrade_settings {
      max_surge = "1"
    }
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks.id]
  }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
    pod_cidr            = "10.244.0.0/16"
    service_cidr        = "10.96.0.0/16"
    dns_service_ip      = "10.96.0.10"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }
  depends_on = [azurerm_role_assignment.network, azurerm_subnet_network_security_group_association.nodes]
}
