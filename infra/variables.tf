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
