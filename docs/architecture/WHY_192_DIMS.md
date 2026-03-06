# Why 192 Dimensions

## GPU Alignment

192 is divisible by 8 and 64 — aligns to GPU tensor cores for efficient matrix multiplication during SimCLR training. This is a practical engineering constraint, not a modeling one.

## Representational Capacity

We expect 4–6 primary behavioral cohorts (FRAUD_BOT, HIGH_INTENT, MEDIUM_INTENT, LOW_INTENT, plus potentially sub-cohorts for mobile/desktop, geo segments, etc.). 192 dimensions provides sufficient capacity to represent ~20 distinguishable cohorts with clear inter-cluster separation, giving headroom for future segmentation without retraining.

## Storage Cost

A 192-dim float32 vector = 192 × 4 bytes = 768 bytes raw. With Upstash Vector overhead, approximately 1.5KB per session. 10,000 sessions/month = 15MB — negligible cost at Upstash's pricing.

## The Constraint

**Do not change this value after the first vector is upserted.** The Upstash Vector index dimension is immutable. Changing it requires creating a new index and re-encoding all historical sessions.
