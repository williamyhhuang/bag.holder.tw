output "runner_sa_email" {
  description = "Cloud Run runner service account email"
  value       = google_service_account.runner.email
}

output "artifact_registry_url" {
  description = "Docker image base URL for CI/CD"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repo}"
}

output "tf_state_bucket" {
  description = "GCS bucket storing Terraform state for deployable module"
  value       = google_storage_bucket.tf_state.name
}

output "data_bucket" {
  description = "GCS bucket for stock CSV data"
  value       = google_storage_bucket.data.name
}

output "wif_provider" {
  description = "WIF provider resource name — set as GitHub secret WIF_PROVIDER (only if create_wif_pool=true)"
  value       = var.create_wif_pool ? google_iam_workload_identity_pool_provider.github[0].name : "WIF managed externally"
}
