#!/bin/bash
# Metricade Production Deployment Checklist
# Run these commands manually in order. Do NOT run this file as a script.

# ============================================================
# PRE-DEPLOYMENT
# ============================================================

# 1. Scale down old vector-worker (stop it from consuming streams)
fly scale count 0 --app behavioral-inference

# 2. Verify old worker is stopped
fly status --app behavioral-inference

# ============================================================
# DEPLOY FEATURE-WORKER
# ============================================================

# 3. Navigate to feature-worker
cd packages/feature-worker

# 4. Create the app on Fly (first time only — skip if already created)
fly apps create metricade-feature-worker

# 5. Set secrets (replace with actual values)
fly secrets set \
  UPSTASH_REDIS_URL="https://singular-fawn-58838.upstash.io" \
  UPSTASH_REDIS_TOKEN="<your-token>" \
  --app metricade-feature-worker

# 6. Deploy
fly deploy --app metricade-feature-worker

# 7. Verify health
curl https://metricade-feature-worker.fly.dev/health

# 8. Check logs for stream discovery
fly logs --app metricade-feature-worker --no-tail 2>&1 | tail -30

# ============================================================
# DEPLOY MODEL-WORKER
# ============================================================

# 9. Navigate to model-worker
cd ../model-worker

# 10. Create the app on Fly (first time only — skip if already created)
fly apps create metricade-model-worker

# 11. Set secrets (replace with actual values)
fly secrets set \
  UPSTASH_REDIS_URL="https://singular-fawn-58838.upstash.io" \
  UPSTASH_REDIS_TOKEN="<your-token>" \
  UPSTASH_VECTOR_URL="https://bright-tiger-54944-us1-vector.upstash.io" \
  UPSTASH_VECTOR_TOKEN="<your-vector-token>" \
  --app metricade-model-worker

# 12. Deploy
fly deploy --app metricade-model-worker

# 13. Verify health
curl https://metricade-model-worker.fly.dev/health

# 14. Check logs for stream discovery and model loading
fly logs --app metricade-model-worker --no-tail 2>&1 | tail -30

# ============================================================
# POST-DEPLOYMENT VALIDATION
# ============================================================

# 15. Browse sukoonfit.com manually — wait 30 seconds for flush

# 16. Check feature-worker processed it
fly logs --app metricade-feature-worker --no-tail 2>&1 | grep "Stored features"

# 17. Check model-worker picked it up
fly logs --app metricade-model-worker --no-tail 2>&1 | grep "Upserted vector"

# 18. Verify vector in Upstash Vector (use the Python one-liner from CLAUDE.md)

# ============================================================
# ROLLBACK (if something breaks)
# ============================================================

# Scale down new workers
fly scale count 0 --app metricade-feature-worker
fly scale count 0 --app metricade-model-worker

# Scale old worker back up
fly scale count 1 --app behavioral-inference
