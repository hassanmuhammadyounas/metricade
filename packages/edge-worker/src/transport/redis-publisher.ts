import { Env } from '../index';
import { publishToDlq } from './dlq';

// XADD to behavioral_stream, check consumer count before publishing
export async function publishToStream(env: Env, message: unknown): Promise<void> {
  const consumerCount = await getConsumerCount(env);

  if (consumerCount === 0) {
    // No active consumers — route to DLQ to prevent message loss
    await publishToDlq(env, message);
    return;
  }

  const body = JSON.stringify(message);
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/xadd/${env.STREAM_NAME}/*`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(['payload', body]),
  });

  if (!res.ok) {
    throw new Error(`Redis XADD failed: ${res.status}`);
  }
}

async function getConsumerCount(env: Env): Promise<number> {
  try {
    // Check heartbeat key — if missing or stale, treat as no consumers
    const res = await fetch(`${env.UPSTASH_REDIS_URL}/get/${env.HEARTBEAT_KEY}`, {
      headers: { Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}` },
    });
    const { result } = await res.json<{ result: string | null }>();
    if (!result) return 0;

    const lastHeartbeat = parseInt(result, 10);
    const timeoutMs = parseInt(env.HEARTBEAT_TIMEOUT_S, 10) * 1000;
    return Date.now() - lastHeartbeat < timeoutMs ? 1 : 0;
  } catch {
    return 0;
  }
}
