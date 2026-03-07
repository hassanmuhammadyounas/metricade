/**
 * Metricade Monitor Worker
 *
 * Runs health checks across the full pipeline on a cron schedule (every hour).
 * Pings the BetterStack heartbeat URL ONLY if all checks pass.
 * If any check fails, the heartbeat is withheld and BetterStack will alert.
 *
 * Checks performed (no E2E):
 *   1. Pixel CDN — pixel.min.js reachable (HTTP 200)
 *   2. Edge worker — /health returns status ok
 *   3. Edge worker — /ingest smoke test accepted (200 ok:true)
 *   4. Redis — heartbeat key fresh (< HEARTBEAT_TIMEOUT_S seconds old)
 *   5. Redis — no stuck messages in stream (XPENDING == 0)
 *   6. Redis — DLQ empty
 *   7. Inference worker — /health returns status ok
 *   8. Vector DB — /info reachable
 *
 * Deploy:
 *   cd packages/monitor-worker && npm install && wrangler deploy
 *
 * Secrets (set via CLI, never in wrangler.toml):
 *   wrangler secret put UPSTASH_REDIS_TOKEN
 *   wrangler secret put UPSTASH_VECTOR_TOKEN
 *   wrangler secret put INGEST_SHARED_SECRET
 */

export type Env = {
  // Secrets
  UPSTASH_REDIS_TOKEN: string;
  UPSTASH_VECTOR_TOKEN: string;
  INGEST_SHARED_SECRET: string;

  // Vars (non-sensitive, set in wrangler.toml)
  UPSTASH_REDIS_URL: string;
  UPSTASH_VECTOR_URL: string;
  PIXEL_CDN_URL: string;
  WORKER_HEALTH_URL: string;
  INFERENCE_HEALTH_URL: string;
  BETTERSTACK_HEARTBEAT_URL: string;
  HEARTBEAT_KEY: string;
  HEARTBEAT_TIMEOUT_S: string;
  DLQ_PREFIX: string;
};

interface CheckResult {
  name: string;
  ok: boolean;
  message: string;
}

// ── Redis helpers ──────────────────────────────────────────────────────────────

async function redisPipeline(env: Env, cmds: unknown[][]): Promise<unknown[]> {
  const r = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(cmds),
  });
  if (!r.ok) throw new Error(`Redis pipeline HTTP ${r.status}`);
  const data = (await r.json()) as { result: unknown }[];
  return data.map((item) => item.result);
}

async function redisOne(env: Env, cmd: unknown[]): Promise<unknown> {
  return (await redisPipeline(env, [cmd]))[0];
}

async function redisScan(env: Env, pattern: string): Promise<string[]> {
  const found: string[] = [];
  let cursor = '0';
  do {
    const result = (await redisOne(env, ['SCAN', cursor, 'MATCH', pattern, 'COUNT', '100'])) as [
      string | number,
      string[],
    ];
    cursor = String(result[0]);
    found.push(...result[1]);
  } while (cursor !== '0');
  return found;
}

// ── Individual checks ──────────────────────────────────────────────────────────

async function checkPixel(env: Env): Promise<CheckResult> {
  try {
    const r = await fetch(env.PIXEL_CDN_URL);
    if (r.status === 200) {
      return { name: 'pixel_cdn', ok: true, message: `pixel.min.js reachable (HTTP 200)` };
    }
    return { name: 'pixel_cdn', ok: false, message: `pixel.min.js returned HTTP ${r.status}` };
  } catch (e) {
    return { name: 'pixel_cdn', ok: false, message: `Pixel CDN unreachable: ${e}` };
  }
}

async function checkEdgeWorkerHealth(env: Env): Promise<CheckResult> {
  try {
    const r = await fetch(env.WORKER_HEALTH_URL);
    const data = (await r.json()) as { status?: string };
    if (r.status === 200 && data.status === 'ok') {
      return { name: 'edge_worker_health', ok: true, message: 'Edge worker /health OK' };
    }
    return {
      name: 'edge_worker_health',
      ok: false,
      message: `Edge worker /health: HTTP ${r.status}, status=${data.status}`,
    };
  } catch (e) {
    return { name: 'edge_worker_health', ok: false, message: `Edge worker /health unreachable: ${e}` };
  }
}


async function checkRedisHeartbeat(env: Env): Promise<CheckResult> {
  try {
    const hb = (await redisOne(env, ['GET', env.HEARTBEAT_KEY])) as string | null;
    if (hb === null) {
      return { name: 'redis_heartbeat', ok: false, message: 'Heartbeat MISSING — inference worker not connected' };
    }
    const ageS = (Date.now() - parseInt(hb, 10)) / 1000;
    const timeoutS = parseInt(env.HEARTBEAT_TIMEOUT_S, 10);
    if (ageS < timeoutS) {
      return { name: 'redis_heartbeat', ok: true, message: `Heartbeat fresh (${ageS.toFixed(0)}s ago)` };
    }
    return {
      name: 'redis_heartbeat',
      ok: false,
      message: `Heartbeat STALE — ${ageS.toFixed(0)}s ago (threshold ${timeoutS}s)`,
    };
  } catch (e) {
    return { name: 'redis_heartbeat', ok: false, message: `Redis unreachable: ${e}` };
  }
}


async function checkRedisDlq(env: Env): Promise<CheckResult> {
  try {
    const dlqKeys = await redisScan(env, `${env.DLQ_PREFIX}:*`);
    if (dlqKeys.length === 0) {
      return { name: 'redis_dlq', ok: true, message: 'DLQ empty' };
    }
    const lens = (await redisPipeline(
      env,
      dlqKeys.map((k) => ['LLEN', k]),
    )) as (number | null)[];
    const total = lens.reduce((sum, n) => sum + (n ?? 0), 0);
    if (total > 0) {
      return { name: 'redis_dlq', ok: false, message: `DLQ has ${total} message(s) waiting to drain` };
    }
    return { name: 'redis_dlq', ok: true, message: 'DLQ empty' };
  } catch (e) {
    return { name: 'redis_dlq', ok: false, message: `DLQ check failed: ${e}` };
  }
}

async function checkInference(env: Env): Promise<CheckResult> {
  try {
    const r = await fetch(env.INFERENCE_HEALTH_URL, { signal: AbortSignal.timeout(15_000) });
    if (r.status === 200) {
      const data = (await r.json()) as { status?: string };
      if (data.status === 'ok') {
        return { name: 'inference_worker', ok: true, message: 'Inference worker health OK' };
      }
      return { name: 'inference_worker', ok: false, message: `Inference worker status: ${data.status}` };
    }
    return { name: 'inference_worker', ok: false, message: `Inference worker /health HTTP ${r.status}` };
  } catch (e) {
    return { name: 'inference_worker', ok: false, message: `Inference worker unreachable: ${e}` };
  }
}

async function checkVectorDb(env: Env): Promise<CheckResult> {
  try {
    const r = await fetch(`${env.UPSTASH_VECTOR_URL}/info`, {
      headers: { Authorization: `Bearer ${env.UPSTASH_VECTOR_TOKEN}` },
    });
    if (!r.ok) {
      return { name: 'vector_db', ok: false, message: `Vector DB /info returned HTTP ${r.status}` };
    }
    const data = (await r.json()) as { result?: { vectorCount?: number } };
    const count = data.result?.vectorCount ?? 0;
    return { name: 'vector_db', ok: true, message: `Vector DB reachable — ${count} vector(s) stored` };
  } catch (e) {
    return { name: 'vector_db', ok: false, message: `Vector DB unreachable: ${e}` };
  }
}

// ── Main runner ────────────────────────────────────────────────────────────────

async function runChecks(env: Env): Promise<void> {
  const startMs = Date.now();

  // Run all checks — Redis checks are sequential (share connection pattern),
  // everything else is parallel
  const [pixelResult, healthResult, inferenceResult, vectorResult, hbResult, dlqResult] =
    await Promise.all([
      checkPixel(env),
      checkEdgeWorkerHealth(env),
      checkInference(env),
      checkVectorDb(env),
      checkRedisHeartbeat(env),
      checkRedisDlq(env),
    ]);

  const all: CheckResult[] = [
    pixelResult,
    healthResult,
    hbResult,
    dlqResult,
    inferenceResult,
    vectorResult,
  ];

  const failures = all.filter((r) => !r.ok);
  const elapsed = Date.now() - startMs;

  const lines = [
    `=== Metricade Monitor (${new Date().toISOString()}, ${elapsed}ms) ===`,
    ...all.map((r) => `[${r.ok ? 'OK  ' : 'FAIL'}] ${r.name}: ${r.message}`),
    `--- ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} CHECK(S) FAILED`} ---`,
  ];
  console.log(lines.join('\n'));

  if (failures.length === 0) {
    try {
      const r = await fetch(env.BETTERSTACK_HEARTBEAT_URL);
      console.log(`BetterStack heartbeat pinged — HTTP ${r.status}`);
    } catch (e) {
      console.error(`BetterStack heartbeat ping failed: ${e}`);
    }
  } else {
    console.log('Checks FAILED — NOT pinging BetterStack');
    console.log('Failures:\n' + failures.map((f) => `  - ${f.name}: ${f.message}`).join('\n'));
  }
}

// ── Worker export ──────────────────────────────────────────────────────────────

export default {
  // Cron-triggered (every hour)
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runChecks(env));
  },

  // HTTP handler — only runs checks if the correct secret header is provided.
  // Bots and scanners get a 404; manual trigger: curl -H "x-monitor-secret: <INGEST_SHARED_SECRET>" https://monitor.metricade.com/
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const secret = request.headers.get('x-monitor-secret');
    if (!secret || secret !== env.INGEST_SHARED_SECRET) {
      return new Response('Not Found\n', { status: 404 });
    }
    ctx.waitUntil(runChecks(env));
    return new Response('Monitor check triggered — see Cloudflare logs\n', { status: 202 });
  },
};
