# Monitoring

## Dashboards

| File | Shows |
|---|---|
| `dashboards/pipeline-health.json` | Events/min, DLQ depth, inference lag |
| `dashboards/fraud-detections.json` | FRAUD_BOT cluster growth over time |
| `dashboards/vector-store.json` | Total vectors, cluster label distribution |

## Alerts

| Alert | Condition | Severity |
|---|---|---|
| `dlq-nonempty` | DLQ > 0 for > 5 minutes | Warning |
| `heartbeat-missing` | fly_worker_heartbeat > 60s old | Critical |
| `worker-error-rate` | CF Worker 5xx rate > 1% | Critical |
| `inference-lag` | Redis Stream pending > 1000 | Warning |

## Alert Thresholds Rationale

- **DLQ > 0 for > 5 min:** A brief DLQ spike (1–2 messages) is expected during Fly.io deploys (rolling). 5 minutes means a genuine outage.
- **Heartbeat > 60s:** Heartbeat writes every 30s. Missing for 60s means at least one full cycle was missed — worker likely down.
- **5xx > 1%:** Normal CF Worker error rate should be < 0.1%. 1% threshold catches genuine bugs without false positives from transient network issues.
- **Pending > 1000:** At 10 events/session, this represents ~100 sessions queued. Inference lag > 100 sessions means the worker is falling behind.

## DLQ Operations

All DLQ inspection, drain, and discard operations are performed manually via the Upstash Redis console or REST API. See [dlq/README.md](dlq/README.md) for the procedures.
