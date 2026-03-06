output "worker_url" {
  description = "Cloudflare Worker ingestion URL"
  value       = module.cloudflare.worker_url
}

output "worker_id" {
  description = "Cloudflare Worker script ID"
  value       = module.cloudflare.worker_id
}

output "fly_app_hostname" {
  description = "Fly.io inference worker hostname"
  value       = module.flyio.app_hostname
}

output "fly_app_id" {
  description = "Fly.io application ID"
  value       = module.flyio.app_id
}

output "redis_url" {
  description = "Upstash Redis URL"
  value       = module.upstash.redis_url
  sensitive   = true
}

output "redis_token" {
  description = "Upstash Redis REST token"
  value       = module.upstash.redis_token
  sensitive   = true
}

output "vector_url" {
  description = "Upstash Vector URL"
  value       = module.upstash.vector_url
  sensitive   = true
}

output "vector_token" {
  description = "Upstash Vector REST token"
  value       = module.upstash.vector_token
  sensitive   = true
}
