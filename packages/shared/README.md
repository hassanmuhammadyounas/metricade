# shared — Cross-Service Contracts

JSON schemas and TypeScript constants shared across all packages. These are the source of truth for inter-service data contracts.

## Schema files

| File | Describes |
|---|---|
| `schema/event-payload.schema.json` | What pixel.js sends to the Worker |
| `schema/stream-message.schema.json` | What the Worker puts in Redis Streams |
| `schema/vector-metadata.schema.json` | What the inference worker stores per vector |
| `schema/trace-id.schema.md` | trace_id format specification |

## Constants

| File | Contains |
|---|---|
| `constants/stream-names.ts` | Redis stream/key names |
| `constants/cluster-labels.ts` | FRAUD_BOT, HIGH_INTENT, etc. |
| `constants/feature-list.ts` | All 51 features in order — must match featurizer.py |
