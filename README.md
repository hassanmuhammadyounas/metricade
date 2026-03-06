# Behavioral Intelligence System

A self-supervised behavioral intelligence platform that collects granular user interaction data from web browsers, encodes it into high-dimensional vector representations using a Transformer neural network, and clusters those vectors to automatically identify distinct behavioral cohorts — including fraud bots, high-intent buyers, casual browsers, and non-commercial visitors — without requiring labeled training data.

## Architecture

```
Browser (pixel.js)
    └─> Cloudflare Edge Worker (Hono)  POST /ingest
            └─> Upstash Redis Streams  (behavioral_stream)
                    └─> Fly.io Inference Worker  (Transformer → 192-dim vector)
                            └─> Upstash Vector  (ANN search, cosine similarity)
                                    └─> Clustering Job  (HDBSCAN, nightly)
```

## Setup

All deployment, infrastructure provisioning, and operations are handled manually. Follow the steps below in order.

**1. Copy and fill environment variables**
```
cp .env.example .env
# Edit .env with your Cloudflare, Fly.io, and Upstash credentials
```

**2. Provision infrastructure**
```
cp infra/terraform.tfvars.example infra/terraform.tfvars
# Edit terraform.tfvars
cd infra && terraform init && terraform apply
```

**3. Install package dependencies**
```
cd packages/pixel && npm install
cd packages/edge-worker && npm install
cd packages/inference-worker && pip install -r requirements.txt
cd packages/clustering-job && pip install -r requirements.txt
```

**4. Deploy edge worker**

See [packages/edge-worker/docs/DEPLOYMENT.md](packages/edge-worker/docs/DEPLOYMENT.md)

**5. Deploy inference worker**

See [packages/inference-worker/docs/DEPLOYMENT.md](packages/inference-worker/docs/DEPLOYMENT.md)

## Packages

| Package | Runtime | Purpose |
|---|---|---|
| `pixel/` | Browser JS | Event collection, buffering, transport |
| `edge-worker/` | Cloudflare Workers (Hono) | Event ingestion API, Redis publish |
| `inference-worker/` | Fly.io Python | Transformer inference, vector upsert |
| `clustering-job/` | Fly.io Python (scheduled) | HDBSCAN clustering, label assignment |
| `shared/` | — | JSON schemas, TypeScript constants |

## Infrastructure

All infrastructure is managed via Terraform in `/infra/`. See [infra/README.md](infra/README.md).

- **Cloudflare Workers** — edge ingestion, zero cold start
- **Fly.io** — inference worker, persistent Redis subscriber
- **Upstash Redis** — Redis Streams for buffered event delivery
- **Upstash Vector** — 192-dim cosine similarity index

## Documentation

- [Architecture Overview](docs/architecture/OVERVIEW.md)
- [Deployment Runbooks](docs/runbooks/)
- [Architecture Decision Records](docs/adr/)
- [Monitoring Guide](monitoring/README.md)

## Deployment

All deployments are performed manually. There is no CI/CD automation. Refer to the deployment docs for each package:

- Edge Worker: [packages/edge-worker/docs/DEPLOYMENT.md](packages/edge-worker/docs/DEPLOYMENT.md)
- Inference Worker: [packages/inference-worker/docs/DEPLOYMENT.md](packages/inference-worker/docs/DEPLOYMENT.md)
- Clustering Job: triggered manually via `fly machine run`
- Infrastructure: `terraform apply` from `infra/`
