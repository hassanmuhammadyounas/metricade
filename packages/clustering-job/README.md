# clustering-job — Scheduled HDBSCAN

Nightly job that fetches all session vectors from Upstash Vector, clusters them with HDBSCAN, assigns behavioral labels, and writes results back to vector metadata.

## Labels

| Label | Criteria |
|---|---|
| `FRAUD_BOT` | scroll_velocity > 180 px/s, y_reversal < 2% |
| `HIGH_INTENT` | scroll_depth > 60%, y_reversal > 5% |
| `MEDIUM_INTENT` | scroll_depth > 30% |
| `LOW_INTENT` | everything else |
| `UNASSIGNED` | HDBSCAN noise points (label -1) |

## Manual trigger

Trigger manually via the Fly.io dashboard or CLI:
```
fly machine run --app behavioral-clustering --image registry.fly.io/behavioral-clustering:latest --rm
```

## View last run

Check `clustering_last_run_stats` key in the Upstash Redis console.

## Tests

```bash
python -m pytest tests/ -v
```
