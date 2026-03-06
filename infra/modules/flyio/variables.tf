variable "fly_api_token" {
  description = "Fly.io API Token"
  type        = string
  sensitive   = true
}

variable "app_name" {
  description = "Fly.io application name"
  type        = string
}

variable "region" {
  description = "Fly.io region — match Upstash region to minimize Redis RTT"
  type        = string
  default     = "iad"
}

variable "vm_memory" {
  description = "VM memory in MB — 256mb is enough for CPU inference at low volume"
  type        = string
  default     = "512"
}
