variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-east1"
}

variable "github_repo" {
  description = "GitHub repo in owner/repo format (used for WIF attribute condition)"
  type        = string
  # e.g. "williamyhhuang/bag.holder.tw"
}

variable "github_actions_sa_email" {
  description = "GitHub Actions deployer service account email (可在不同 GCP 專案)"
  type        = string
  # e.g. "github-actions@github-actions-shared.iam.gserviceaccount.com"
}

variable "create_wif_pool" {
  description = "是否在此專案建立 WIF pool。若 GitHub Actions SA 的 WIF 已在其他專案設定，設為 false"
  type        = bool
  default     = true
}

variable "tf_state_bucket" {
  description = "GCS bucket name for Terraform remote state"
  type        = string
  default     = "bag-holder-tf-state"
}

variable "data_bucket" {
  description = "GCS bucket name for stock CSV data"
  type        = string
  default     = "bag-holder-data"
}

variable "artifact_registry_repo" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "bag-holder-repo"
}
