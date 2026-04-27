output "webhook_url" {
  description = "Public HTTPS URL of the Telegram webhook Cloud Run service"
  value       = module.service_webhook.url
}

output "download_job_name" {
  value = module.job_download.job_name
}

output "signals_job_name" {
  value = module.job_signals.job_name
}
