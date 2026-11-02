# Terraform: VNet, subnet, AKS and identity

Complete the cost and quota checks in chapter 1 first. Infrastructure creation is performed locally by you with Azure CLI credentials. CI validates the code; it does not get subscription-wide provisioning permissions. You need resource creation permission and permission to assign Azure roles for this lab.

The lab uses a Standard cluster with Free control-plane pricing, two 4-vCPU system nodes, Azure CNI Overlay and Cilium network policy. Both system and application pods share this pool to limit scope. Separate system/user pools are an upgrade exercise. No B-series nodes, NAT Gateway, Firewall, Bastion, ACR, managed Grafana, Log Analytics or public application ingress are deployed.

## `infra/versions.tf`

```hcl file=infra/versions.tf
terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.59.0"
    }
  }
}
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
```

## `infra/variables.tf`

```hcl file=infra/variables.tf
variable "subscription_id" {
  type = string
}
variable "location" {
  type    = string
  default = "centralindia"
}
variable "name" {
  type    = string
  default = "shopshield"
}
variable "vm_size" {
  type    = string
  default = "Standard_D4s_v5"
}
variable "admin_group_id" {
  description = "Object ID of an Entra security group containing your human administrator"
  type        = string
}
variable "api_allowed_cidrs" {
  description = "Optional public API allowlist. Empty permits public network access with Entra authentication. Hosted CI requires reachability."
  type        = list(string)
  default     = []
}
```

## `infra/main.tf`

The control-plane managed identity needs Network Contributor on the existing subnet before AKS creation. Kubernetes ClusterIP and overlay pod CIDRs are not Azure subnets. AKS creates its node resource group, load balancer and outbound public IP; do not duplicate those resources here. Standard load-balancer egress incurs charges even though app Services are ClusterIP.

```hcl file=infra/main.tf
resource "azurerm_resource_group" "lab" {
  name     = "rg-${var.name}"
  location = var.location
  tags     = { project = var.name, purpose = "learning" }
}
resource "azurerm_virtual_network" "lab" {
  name                = "vnet-${var.name}"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = ["10.20.0.0/16"]
}
resource "azurerm_subnet" "aks" {
  name                 = "snet-aks-nodes"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.20.0.0/22"]
}
resource "azurerm_network_security_group" "nodes" {
  name                = "nsg-aks-nodes"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
}
resource "azurerm_subnet_network_security_group_association" "nodes" {
  subnet_id                 = azurerm_subnet.aks.id
  network_security_group_id = azurerm_network_security_group.nodes.id
}
resource "azurerm_user_assigned_identity" "aks" {
  name                = "id-${var.name}-controlplane"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
}
resource "azurerm_role_assignment" "network" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.aks.principal_id
}
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
    node_count      = 2
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
resource "azurerm_user_assigned_identity" "deploy" {
  name                = "id-${var.name}-github"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
}
resource "azurerm_role_assignment" "deploy_user" {
  scope                = azurerm_kubernetes_cluster.lab.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = azurerm_user_assigned_identity.deploy.principal_id
}
resource "azurerm_role_assignment" "deploy_namespace" {
  scope                = "${azurerm_kubernetes_cluster.lab.id}/namespaces/shopshield"
  role_definition_name = "Azure Kubernetes Service RBAC Writer"
  principal_id         = azurerm_user_assigned_identity.deploy.principal_id
}
resource "azurerm_role_assignment" "human_admin" {
  scope                = azurerm_kubernetes_cluster.lab.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = var.admin_group_id
}
```

The NSG uses Azure default rules, including deny unsolicited inbound internet traffic and allow VNet traffic/outbound internet. It is not a firewall with restricted egress. Cilium policies in the Helm chart restrict application pods more narrowly. An AKS public API endpoint lives outside this node subnet and needs separate API access controls.

## `infra/outputs.tf`

```hcl file=infra/outputs.tf
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
```

## `infra/terraform.tfvars.example`

```hcl file=infra/terraform.tfvars.example
subscription_id = "REPLACE-WITH-SUBSCRIPTION-ID"
admin_group_id  = "REPLACE-WITH-ENTRA-SECURITY-GROUP-OBJECT-ID"
location       = "centralindia"
vm_size        = "Standard_D4s_v5"
# For local administration only, restrict to your public IP/32.
# Hosted GitHub runners will not be reachable through that allowlist.
api_allowed_cidrs = []
```

## Provision and verify

Create an Entra security group, add yourself and record its object ID. If your tenant prevents this, obtain the group from your tenant administrator. Sign out/in to refresh group claims. Register providers if needed: Microsoft.ContainerService, Microsoft.Compute, Microsoft.Network, Microsoft.ManagedIdentity. Review their registration status first.

```bash
az login
az account set --subscription YOUR_SUBSCRIPTION_ID
cp infra/terraform.tfvars.example infra/terraform.tfvars
# Edit infra/terraform.tfvars with your own values before continuing.
terraform -chdir=infra init
terraform -chdir=infra fmt
terraform -chdir=infra validate
terraform -chdir=infra plan -out=lab.tfplan
# Review resource counts, region, SKU, identity and all expected charges.
terraform -chdir=infra apply lab.tfplan
az aks get-credentials -g rg-shopshield -n aks-shopshield --overwrite-existing
kubelogin convert-kubeconfig -l azurecli
kubectl get nodes -o wide
kubectl get pods -A
```

Install kubelogin from its official Azure release instructions. Wait for role assignment propagation if access returns Forbidden. Keep `infra/.terraform.lock.hcl` in Git. State and plans stay local and private; back up state securely until destruction. No kubeconfig is exported by Terraform. There is deliberately no remote-state bootstrap in this individual lab; use Azure Blob state with Entra authentication and locking as a later extension.

An empty API allowlist supports hosted CI but exposes the authenticated endpoint publicly. For a stricter lab use your IP/32 and a trusted self-hosted runner on that network, changing the workflow runner configuration. Never solve CI reachability by granting CI permission to alter subscription network access.
