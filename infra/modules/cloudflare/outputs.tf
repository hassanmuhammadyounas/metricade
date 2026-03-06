output "worker_url" {
  description = "Cloudflare Worker URL"
  value       = "https://your-domain.com/api/behavioral"
}

output "worker_id" {
  description = "Cloudflare Worker script ID"
  value       = cloudflare_worker_script.behavioral_edge.id
}
