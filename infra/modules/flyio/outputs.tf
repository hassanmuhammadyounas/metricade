output "app_hostname" {
  description = "Fly.io application hostname"
  value       = "${fly_app.inference.name}.fly.dev"
}

output "app_id" {
  description = "Fly.io application ID"
  value       = fly_app.inference.id
}
