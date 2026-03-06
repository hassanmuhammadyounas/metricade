resource "cloudflare_worker_script" "behavioral_edge" {
  account_id = var.cf_account_id
  name       = var.worker_name
  content    = file("${path.module}/../../../packages/edge-worker/dist/index.js")
}

resource "cloudflare_worker_route" "ingest_route" {
  zone_id     = var.cf_zone_id
  pattern     = "your-domain.com/api/behavioral/*"
  script_name = cloudflare_worker_script.behavioral_edge.name
}

resource "cloudflare_worker_cron_trigger" "heartbeat" {
  account_id  = var.cf_account_id
  script_name = cloudflare_worker_script.behavioral_edge.name
  schedules   = [var.cron_schedule]
}
