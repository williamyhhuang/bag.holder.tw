variable "name" {
  type = string
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "image" {
  type = string
}

variable "service_account_email" {
  type = string
}

variable "command" {
  type = list(string)
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "task_timeout_seconds" {
  type    = number
  default = 600
}

variable "max_retries" {
  type    = number
  default = 0
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "secret_env_vars" {
  description = "Map of env var name to { secret, version } — mounted from Secret Manager"
  type = map(object({
    secret  = string
    version = string
  }))
  default = {}
}

variable "vpc_subnet_id" {
  description = "Subnetwork self-link for Direct VPC Egress. Leave null to skip VPC."
  type        = string
  default     = null
}
