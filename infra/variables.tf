variable "cf_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "cf_api_token" {
  description = "Cloudflare API Token — requires Workers:Edit, Workers Routes:Edit permissions"
  type        = string
  sensitive   = true
}

variable "cf_zone_id" {
  description = "Cloudflare Zone ID — only required if using custom domain routing"
  type        = string
  default     = ""
}

variable "fly_api_token" {
  description = "Fly.io API Token"
  type        = string
  sensitive   = true
}

variable "fly_app_name" {
  description = "Fly.io application name for the inference worker"
  type        = string
  default     = "behavioral-inference"
}

variable "fly_region" {
  description = "Fly.io region — must match Upstash region to minimise Redis RTT"
  type        = string
  default     = "iad"
}

variable "upstash_email" {
  description = "Upstash account email"
  type        = string
}

variable "upstash_api_key" {
  description = "Upstash API Key"
  type        = string
  sensitive   = true
}

variable "upstash_region" {
  description = "Upstash region — must match fly_region"
  type        = string
  default     = "us-east-1"
}

variable "vector_dims" {
  description = "Transformer output dimension — DO NOT CHANGE after first upsert"
  type        = number
  default     = 192
}

variable "vector_similarity" {
  description = "Vector similarity metric — SimCLR-trained vectors work best with cosine"
  type        = string
  default     = "COSINE"
}
