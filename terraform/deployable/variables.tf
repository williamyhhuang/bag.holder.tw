variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-east1"
}

variable "image" {
  description = "Full Docker image URI with tag, e.g. asia-east1-docker.pkg.dev/PROJECT/bag-holder-repo/bag-holder:SHA"
  type        = string
  # 由 CI/CD 注入，不設 default
}

variable "notification_email" {
  description = "Email address to receive failure notifications (Cloud Scheduler / Workflow / Cloud Run)"
  type        = string
}
