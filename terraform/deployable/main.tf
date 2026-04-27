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

locals {
  # Runner SA email 由 bootstrap 建立，命名固定
  runner_sa_email = "bag-holder-runner@${var.project_id}.iam.gserviceaccount.com"

  common_secret_env_vars = {
    APP_SECRETS = {
      secret  = "APP_SECRETS"
      version = "latest"
    }
  }

  common_env_vars = {
    APP_ENV          = "production"
    PYTHONUNBUFFERED = "1"
  }
}

# ── Cloud Run Job: bag-holder-download ────────────────────────────────────────
module "job_download" {
  source = "../modules/cloud_run_job"

  name                  = "bag-holder-download"
  project_id            = var.project_id
  region                = var.region
  image                 = var.image
  service_account_email = local.runner_sa_email
  command               = ["/entrypoint-download.sh"]
  memory                = "2Gi"
  cpu                   = "2"
  task_timeout_seconds  = 3600
  max_retries           = 1
  secret_env_vars       = local.common_secret_env_vars
  env_vars              = local.common_env_vars
}

# ── Cloud Run Job: bag-holder-signals ─────────────────────────────────────────
module "job_signals" {
  source = "../modules/cloud_run_job"

  name                  = "bag-holder-signals"
  project_id            = var.project_id
  region                = var.region
  image                 = var.image
  service_account_email = local.runner_sa_email
  command               = ["/entrypoint-signals.sh"]
  memory                = "2Gi"
  cpu                   = "2"
  task_timeout_seconds  = 600
  max_retries           = 1
  secret_env_vars       = local.common_secret_env_vars
  env_vars              = local.common_env_vars
}

# ── Cloud Run Service: bag-holder-webhook ─────────────────────────────────────
module "service_webhook" {
  source = "../modules/cloud_run_service"

  name                  = "bag-holder-webhook"
  project_id            = var.project_id
  region                = var.region
  image                 = var.image
  service_account_email = local.runner_sa_email
  command               = ["/entrypoint-webhook.sh"]
  memory                = "512Mi"
  cpu                   = "1"
  min_instances         = 0
  max_instances         = 3
  concurrency           = 80
  timeout_seconds       = 30
  allow_unauthenticated = true
  secret_env_vars       = local.common_secret_env_vars
  env_vars              = local.common_env_vars
}

# ── GCP Workflows: download → signals 依序執行 ───────────────────────────────
resource "google_workflows_workflow" "run_jobs" {
  name            = "bag-holder-run-jobs"
  region          = var.region
  project         = var.project_id
  service_account = local.runner_sa_email
  source_contents = file("${path.module}/run-jobs.workflow.yaml")

  depends_on = [module.job_download, module.job_signals]
}

# ── Cloud Scheduler → GCP Workflows ──────────────────────────────────────────
# 台北時間 08:05 週一至週五（UTC 00:05）
resource "google_cloud_scheduler_job" "run_jobs" {
  name             = "bag-holder-run-jobs-trigger"
  region           = var.region
  project          = var.project_id
  schedule         = "5 0 * * 1-5"
  time_zone        = "Asia/Taipei"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/${google_workflows_workflow.run_jobs.id}/executions"
    body        = base64encode("{}")

    oauth_token {
      service_account_email = local.runner_sa_email
    }
  }

  depends_on = [google_workflows_workflow.run_jobs]
}
