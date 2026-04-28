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
# 台北時間 08:05 週一至週五
resource "google_cloud_scheduler_job" "run_jobs" {
  name             = "bag-holder-run-jobs-trigger"
  region           = var.region
  project          = var.project_id
  schedule         = "5 8 * * 1-5"
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

# ── Monitoring: Email notification channel ────────────────────────────────────
resource "google_monitoring_notification_channel" "email" {
  display_name = "bag-holder failure alerts"
  type         = "email"
  project      = var.project_id
  labels = {
    email_address = var.notification_email
  }
}

# ── Monitoring: Log-based metrics ─────────────────────────────────────────────
resource "google_logging_metric" "scheduler_failure" {
  name    = "bag_holder/scheduler_failure"
  project = var.project_id
  filter  = "resource.type=\"cloud_scheduler_job\" AND resource.labels.job_id=\"bag-holder-run-jobs-trigger\" AND severity>=ERROR"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_logging_metric" "workflow_failure" {
  name    = "bag_holder/workflow_failure"
  project = var.project_id
  filter  = "resource.type=\"workflows.googleapis.com/Workflow\" AND resource.labels.workflow_id=\"bag-holder-run-jobs\" AND severity>=ERROR"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_logging_metric" "cloudrun_job_failure" {
  name    = "bag_holder/cloudrun_job_failure"
  project = var.project_id
  filter  = "resource.type=\"cloud_run_job\" AND (resource.labels.job_name=\"bag-holder-download\" OR resource.labels.job_name=\"bag-holder-signals\") AND textPayload=\"Container called exit(1).\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

# ── Monitoring: Alert policies ─────────────────────────────────────────────────
resource "google_monitoring_alert_policy" "scheduler_failure" {
  display_name          = "[bag-holder] Cloud Scheduler 失敗"
  project               = var.project_id
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "Cloud Scheduler job failed to trigger"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/bag_holder/scheduler_failure\" AND resource.type=\"cloud_scheduler_job\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }
}

resource "google_monitoring_alert_policy" "workflow_failure" {
  display_name          = "[bag-holder] GCP Workflow 失敗"
  project               = var.project_id
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "Workflow execution failed"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/bag_holder/workflow_failure\" AND resource.type=\"workflows.googleapis.com/Workflow\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }
}

resource "google_monitoring_alert_policy" "cloudrun_job_failure" {
  display_name          = "[bag-holder] Cloud Run Job 失敗"
  project               = var.project_id
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "Cloud Run job task exited with error"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/bag_holder/cloudrun_job_failure\" AND resource.type=\"cloud_run_job\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  alert_strategy {
    auto_close = "604800s"
  }
}
