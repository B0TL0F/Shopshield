variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "centralindia"
}

variable "storage_account_name" {
  type        = string
  description = "Globally unique state account name; use the existing name if importing"
  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "Use 3-24 lowercase letters or digits."
  }
}

variable "operator_object_id" {
  type        = string
  description = "Entra object ID of the human user who runs Terraform"
}
