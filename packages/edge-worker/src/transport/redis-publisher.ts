import { Env } from '../index';
import { publishToDlq } from './dlq';

// XADD to behavioral_stream:{org_id}, check consumer heartbeat before publishing
export async function publishToStream(env: Env, orgId: string, message: unknown): Promise<void> {
  const streamKey = `${env.STREAM_NAME}:${orgId}`;
  const consumerAlive = await isConsumerAlive(env);

  if (!consumerAlive) {
    // No active consumer — route to DLQ to prevent message loss
    await publishToDlq(env, orgId, message);
    return;
  }

  const body = JSON.stringify(message);
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify([
      ['XADD', streamKey, '*', 'payload', body],
      ['INCR', `metricade_ingest_total:${orgId}`],
    ]),
  });

  if (!res.ok) {
    throw new Error(`Redis XADD failed: ${res.status}`);
  }
}

async function isConsumerAlive(env: Env): Promise<boolean> {
  try {
    const res = await fetch(`${env.UPSTASH_REDIS_URL}/get/${env.HEARTBEAT_KEY}`, {
      headers: { Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}` },
    });
    const { result } = await res.json<{ result: string | null }>();
    if (!result) return false;
    const lastHeartbeat = parseInt(result, 10);
    const timeoutMs = parseInt(env.HEARTBEAT_TIMEOUT_S, 10) * 1000;
    return Date.now() - lastHeartbeat < timeoutMs;
  } catch {
    return false;
  }
}
