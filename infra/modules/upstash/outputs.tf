output "redis_url" {
  description = "Upstash Redis REST URL"
  value       = upstash_redis_database.behavioral.endpoint
  sensitive   = true
}

output "redis_token" {
  description = "Upstash Redis REST token"
  value       = upstash_redis_database.behavioral.rest_token
  sensitive   = true
}

output "vector_url" {
  description = "Upstash Vector REST URL"
  value       = upstash_vector_index.fingerprints.endpoint
  sensitive   = true
}

output "vector_token" {
  description = "Upstash Vector REST token"
  value       = upstash_vector_index.fingerprints.token
  sensitive   = true
}
