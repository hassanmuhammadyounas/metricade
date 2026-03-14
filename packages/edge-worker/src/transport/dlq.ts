import { Env } from '../index';

// LPUSH to metricade_dlq:{org_id} — last-resort fallback when XADD fails
export async function publishToDlq(env: Env, orgId: string, message: unknown): Promise<void> {
  const dlqKey = `${env.DLQ_KEY}:${orgId}`;
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify([
      ['LPUSH', dlqKey, JSON.stringify(message)],
    ]),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Redis DLQ LPUSH failed [${res.status}]: ${text}`);
  }
}
