terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable Required APIs ───────────────────────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "workflows.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ── GCS: Terraform State Bucket ────────────────────────────────────────────────
resource "google_storage_bucket" "tf_state" {
  name                        = var.tf_state_bucket
  location                    = var.region
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# ── GCS: Application Data Bucket ──────────────────────────────────────────────
resource "google_storage_bucket" "data" {
  name                        = var.data_bucket
  location                    = var.region
  uniform_bucket_level_access = true

  depends_on = [google_project_service.apis]
}

# ── Artifact Registry ─────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "app" {
  repository_id = var.artifact_registry_repo
  location      = var.region
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# ── Service Account: Cloud Run Runner ────────────────────────────────────────
resource "google_service_account" "runner" {
  account_id   = "bag-holder-runner"
  display_name = "Bag Holder Cloud Run Runner"
}

# ── IAM: Runner SA permissions ────────────────────────────────────────────────
resource "google_project_iam_member" "runner_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# Cloud Scheduler → GCP Workflows → Cloud Run Jobs 需要 run.invoker
resource "google_project_iam_member" "runner_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# Cloud Scheduler 觸發 Workflows 需要 workflows.invoker
resource "google_project_iam_member" "runner_workflows_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_storage_bucket_iam_member" "runner_gcs_read" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_storage_bucket_iam_member" "runner_gcs_write" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.runner.email}"
}

# ── IAM: Deployer SA permissions (GitHub Actions SA，可在不同專案) ───────────
resource "google_project_iam_member" "deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${var.github_actions_sa_email}"
}

resource "google_project_iam_member" "deployer_scheduler_admin" {
  project = var.project_id
  role    = "roles/cloudscheduler.admin"
  member  = "serviceAccount:${var.github_actions_sa_email}"
}

resource "google_project_iam_member" "deployer_workflows_admin" {
  project = var.project_id
  role    = "roles/workflows.admin"
  member  = "serviceAccount:${var.github_actions_sa_email}"
}

resource "google_project_iam_member" "deployer_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${var.github_actions_sa_email}"
}

# Deployer 需要能將 runner SA 指派給 Cloud Run 資源
resource "google_service_account_iam_member" "deployer_impersonate_runner" {
  service_account_id = google_service_account.runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.github_actions_sa_email}"
}

# Deployer 需要讀寫 Terraform state bucket
resource "google_storage_bucket_iam_member" "deployer_tf_state" {
  bucket = google_storage_bucket.tf_state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.github_actions_sa_email}"
}

# ── WIF (可選): 若 WIF 已在其他專案設定則跳過 ──────────────────────────────
resource "google_iam_workload_identity_pool" "github" {
  count                     = var.create_wif_pool ? 1 : 0
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.create_wif_pool ? 1 : 0
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "wif_binding" {
  count              = var.create_wif_pool ? 1 : 0
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.github_actions_sa_email}"
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repo}"
}

# ── Secret Manager: APP_SECRETS shell ─────────────────────────────────────────
# 只建立 secret 殼，實際值需手動填入：
# gcloud secrets versions add APP_SECRETS --data-file=secrets.json
resource "google_secret_manager_secret" "app_secrets" {
  secret_id = "APP_SECRETS"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}
