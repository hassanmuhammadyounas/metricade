variable "upstash_email" {
  description = "Upstash account email"
  type        = string
}

variable "upstash_api_key" {
  description = "Upstash API Key"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "Upstash region — must match fly_region to minimize RTT"
  type        = string
  default     = "us-east-1"
}

variable "vector_dimensions" {
  description = "Vector index dimension count — must match Transformer output dim. DO NOT CHANGE after first upsert."
  type        = number
  default     = 192
}

variable "vector_similarity" {
  description = "Similarity function — COSINE for SimCLR-trained vectors"
  type        = string
  default     = "COSINE"
}
