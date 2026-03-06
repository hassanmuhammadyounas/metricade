variable "cf_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "cf_api_token" {
  description = "Cloudflare API Token"
  type        = string
  sensitive   = true
}

variable "cf_zone_id" {
  description = "Cloudflare Zone ID"
  type        = string
  default     = ""
}

variable "worker_name" {
  description = "Cloudflare Worker script name"
  type        = string
}

variable "cron_schedule" {
  description = "Cron expression for Worker scheduled trigger"
  type        = string
  default     = "*/1 * * * *"
}
