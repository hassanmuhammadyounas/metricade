# trace_id Format

**Pattern:** `{session_id}_{flush_counter}_{timestamp_ms}`

**Example:** `a1b2c3d4-e5f6-7890-abcd-ef1234567890_3_1709000000000`

## Components

| Part | Source | Description |
|---|---|---|
| `session_id` | sessionStorage | UUID, unique per tab |
| `flush_counter` | In-memory int | Increments on every flush within a session |
| `timestamp_ms` | `Date.now()` | Unix timestamp at flush time |

## Purpose

- Links a stream message to its originating pixel flush
- Enables correlation across Worker logs, Redis stream, and Vector metadata
- `flush_counter` distinguishes multiple flushes from the same session
