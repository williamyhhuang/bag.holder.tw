# ──────────────────────────────────────────────────────────────────────────────
# GCE Spot VM: MTX 自動交易（日盤 + 夜盤）
#
# 取代原本兩個 Cloud Run Jobs（bag-holder-mtx-trader-day / -night）。
# Cloud Run 按秒計費，WebSocket 長連線每天常駐 ~19 小時 → 每天 ~NT$60；
# 改用 e2-small Spot VM 約 NT$210/月（省 ~85%）。
#
# 網路：VM 放在現有 subnet、無外部 IP，egress 走現有 Cloud NAT
#       → 富邦 API IP 白名單（bag-holder-nat-ip）完全不變。
#
# 轉實盤：把 provisioning_model 改 "STANDARD"、preemptible 改 false、
#         移除 instance_termination_action、automatic_restart 改 true 即可。
#
# 注意：startup-script 變更會觸發 VM 重啟（allow_stopping_for_update），
#       請挑非交易時段（台北 13:35–14:30）merge。
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # VM 永遠 pull :latest（CI 每次 push 都會更新 :latest tag），
  # 與 var.image 的 SHA tag 解耦，避免每次 deploy 都改 VM metadata 觸發重啟。
  mtx_image_latest = "${split(":", var.image)[0]}:latest"
  mtx_vm_zone      = "${var.region}-b"
  mtx_vm_name      = "bag-holder-mtx-trader"
}

resource "google_compute_instance" "mtx_trader" {
  name         = local.mtx_vm_name
  machine_type = "e2-small"
  zone         = local.mtx_vm_zone
  project      = var.project_id

  scheduling {
    provisioning_model          = "SPOT"
    preemptible                 = true
    automatic_restart           = false
    instance_termination_action = "STOP" # 搶占後 STOP（非 DELETE），keepalive scheduler 可 start 回來
  }

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.cloudrun.id
    # 不設 access_config → 無外部 IP，egress 走 Cloud NAT（白名單 IP 不變）
  }

  service_account {
    email  = local.runner_sa_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    google-logging-enabled    = "true"
    google-monitoring-enabled = "true"
    startup-script            = file("${path.module}/mtx-trader-startup.sh")
    mtx-image                 = local.mtx_image_latest
  }

  allow_stopping_for_update = true
}

# Cloud Scheduler 以 runner SA 呼叫 instances.start/stop，需要 instance 層級權限
resource "google_compute_instance_iam_member" "runner_manage_vm" {
  project       = var.project_id
  zone          = google_compute_instance.mtx_trader.zone
  instance_name = google_compute_instance.mtx_trader.name
  role          = "roles/compute.instanceAdmin.v1"
  member        = "serviceAccount:${local.runner_sa_email}"
}

# ── Keepalive: 定期 instances.start（冪等；已 RUNNING 時回 400 屬預期）────────
# Spot VM 被搶占後 ≤10 分鐘內自動拉回；開機後 startup-script 的 dispatcher
# 會依當下時間補啟動正確的 session。
# 台北 08:00–23:59 週一至週五（涵蓋日盤 + 夜盤前半）
resource "google_cloud_scheduler_job" "mtx_vm_keepalive_day" {
  name             = "bag-holder-mtx-vm-keepalive-day"
  region           = var.region
  project          = var.project_id
  schedule         = "*/10 8-23 * * 1-5"
  time_zone        = "Asia/Taipei"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://compute.googleapis.com/compute/v1/projects/${var.project_id}/zones/${local.mtx_vm_zone}/instances/${local.mtx_vm_name}/start"

    oauth_token {
      service_account_email = local.runner_sa_email
    }
  }

  depends_on = [google_compute_instance.mtx_trader]
}

# 台北 00:00–05:59 週二至週六（夜盤跨日段，週五夜盤延伸到週六凌晨）
resource "google_cloud_scheduler_job" "mtx_vm_keepalive_overnight" {
  name             = "bag-holder-mtx-vm-keepalive-overnight"
  region           = var.region
  project          = var.project_id
  schedule         = "*/10 0-4 * * 2-6"
  time_zone        = "Asia/Taipei"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://compute.googleapis.com/compute/v1/projects/${var.project_id}/zones/${local.mtx_vm_zone}/instances/${local.mtx_vm_name}/start"

    oauth_token {
      service_account_email = local.runner_sa_email
    }
  }

  depends_on = [google_compute_instance.mtx_trader]
}

# ── 週末關機：週六 05:30（夜盤 05:00 已收）→ 週一 08:00 由 keepalive 拉起 ──
resource "google_cloud_scheduler_job" "mtx_vm_weekend_stop" {
  name             = "bag-holder-mtx-vm-weekend-stop"
  region           = var.region
  project          = var.project_id
  schedule         = "30 5 * * 6"
  time_zone        = "Asia/Taipei"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://compute.googleapis.com/compute/v1/projects/${var.project_id}/zones/${local.mtx_vm_zone}/instances/${local.mtx_vm_name}/stop"

    oauth_token {
      service_account_email = local.runner_sa_email
    }
  }

  depends_on = [google_compute_instance.mtx_trader]
}

# ── 防火牆: IAP SSH（除錯用，VM 無外部 IP 只能走 IAP tunnel）──────────────────
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "bag-holder-allow-iap-ssh"
  network = google_compute_network.vpc.id
  project = var.project_id

  source_ranges = ["35.235.240.0/20"] # IAP 來源範圍

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
