# Edge Worker Routes

## POST /ingest

Main event ingestion endpoint called by pixel.js.

**Input:**
```json
{
  "trace_id": "string",
  "events": [{ "event_type": "SCROLL", "delta_ms": 123, ... }]
}
```

**Output (200):**
```json
{ "ok": true, "trace_id": "string" }
```

**Errors:**
- `400` — invalid JSON body
- `500` — Redis publish failure

---

## GET /health

Returns subsystem health status.

**Output (200):**
```json
{
  "status": "ok | degraded",
  "timestamp": "ISO8601",
  "redis_ping": true,
  "version": "1.0.0"
}
```

---

## GET /dlq/status

Returns dead letter queue stats. Requires `x-ingest-secret` header.

**Output (200):**
```json
{
  "dlq_count": 0,
  "oldest_message_age_ms": null
}
```

**Errors:**
- `401` — missing or invalid `x-ingest-secret`
