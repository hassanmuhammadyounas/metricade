# Why Cloudflare Edge for Ingestion

## delta_ms Fidelity Argument

The most powerful fraud signal is `delta_ms` — milliseconds between consecutive events. A fraud bot produces machine-precise timing (340ms ± 2ms). A human produces noisy timing (200–800ms with high variance).

For this signal to be meaningful, the server must receive events with minimal latency distortion. If the browser sends events at t=0 and t=340ms but the server receives them at t=0+RTT and t=340+RTT, the delta_ms is preserved. But if RTT variance is high (e.g. 50ms jitter), delta_ms values below ~100ms become unreliable.

Cloudflare Workers run at the nearest PoP — typically < 20ms RTT from any browser. The RTT variance is low and consistent. This preserves sub-100ms delta_ms signals that would be lost with a centralized origin server.

## Zero Cold Start

Workers run in V8 isolates with sub-millisecond initialization. There is no cold start problem. Every request is handled immediately, even at low traffic volumes. This matters for a fraud detection system that may see bursty traffic from bot attacks.
