# Infrastructure (Terraform)

Every resource — Cloudflare, Fly.io, Upstash — is declared here. `terraform apply` provisions everything from scratch.

## Usage

```bash
# Initialize providers
terraform init

# Preview changes
terraform plan -var-file=terraform.tfvars

# Apply
terraform apply -var-file=terraform.tfvars

# Destroy all resources
terraform destroy -var-file=terraform.tfvars
```

## Setup

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your credentials — never commit this file
```

## Modules

| Module | Provisions |
|---|---|
| `modules/cloudflare/` | Worker script, routes, cron triggers |
| `modules/flyio/` | Fly app, VM size, region, scaling |
| `modules/upstash/` | Redis database, Vector index (192 dims, cosine) |
