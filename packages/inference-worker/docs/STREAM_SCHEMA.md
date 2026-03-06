# Redis Stream Message Schema

Every message in `behavioral_stream` has exactly one field: `payload` (JSON string).

## Payload structure

```json
{
  "trace_id": "string",
  "received_at": 1709000000000,
  "ip_meta": {
    "ip": "string",
    "ip_type": "residential | datacenter | vpn | tor | unknown",
    "ip_country": "string",
    "ip_asn": "string"
  },
  "ua_meta": {
    "browser_family": "chrome | firefox | safari | edge | other",
    "os_family": "windows | macos | ios | android | linux | other",
    "device_type": "desktop | mobile | tablet | bot | unknown",
    "is_webview": false,
    "webview_type": null
  },
  "time_features": {
    "hour_sin": 0.0,
    "hour_cos": 1.0,
    "dow_sin": 0.0,
    "dow_cos": 1.0
  },
  "payload": {
    "trace_id": "string",
    "events": [...]
  }
}
```
