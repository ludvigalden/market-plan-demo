# Name prefix shared with the bootstrap root.
variable "prefix" {
  type = string
}

# Object ID of the CD service principal the bootstrap root created. It gets
# the data-plane role that lets the deploy workflow run the live eval.
variable "cd_principal_object_id" {
  type = string
}

# Object ID of the person who runs Terraform and the live eval locally.
# Empty turns that role assignment off.
variable "owner_principal_object_id" {
  type    = string
  default = ""
}

# Container image; deploys replace it out of band, which Terraform ignores.
variable "image" {
  type    = string
  default = "mcr.microsoft.com/k8se/quickstart:latest"
}

# Idle replicas. Zero stops the billing between visits at the cost of a
# cold start on the first request; one keeps the demo instant.
variable "min_replicas" {
  type    = number
  default = 0
}

variable "max_replicas" {
  type    = number
  default = 1
}

variable "postgres_version" {
  type    = string
  default = "16"
}

variable "postgres_location" {
  type    = string
  default = "northeurope"
}

# Part of the server name; server names are bound to their first region.
variable "postgres_location_short" {
  type    = string
  default = "ne"
}

variable "chat_model_deployment_name" {
  type    = string
  default = "gpt-6-luna"
}

# Custom hostname served with a managed certificate. Empty leaves the app
# on its generated Container Apps hostname. Its DNS records (a CNAME to
# the app and the asuid TXT verification record) must resolve before the
# apply that sets it.
variable "public_hostname" {
  type    = string
  default = ""
}
