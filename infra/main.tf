terraform {
  required_version = ">= 1.5"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    fly = {
      source  = "fly-apps/fly"
      version = "~> 0.0.23"
    }
    upstash = {
      source  = "upstash/upstash"
      version = "~> 1.5"
    }
  }
}

module "cloudflare" {
  source         = "./modules/cloudflare"
  cf_account_id  = var.cf_account_id
  cf_api_token   = var.cf_api_token
  cf_zone_id     = var.cf_zone_id
  worker_name    = "behavioral-edge-worker"
  cron_schedule  = "*/1 * * * *"
}

module "flyio" {
  source        = "./modules/flyio"
  fly_api_token = var.fly_api_token
  app_name      = var.fly_app_name
  region        = var.fly_region
  vm_memory     = "512"
}

module "upstash" {
  source            = "./modules/upstash"
  upstash_email     = var.upstash_email
  upstash_api_key   = var.upstash_api_key
  region            = var.upstash_region
  vector_dimensions = var.vector_dims
  vector_similarity = var.vector_similarity
}
