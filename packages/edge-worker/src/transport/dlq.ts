import { Env } from '../index';

// LPUSH to behavioral_dlq when no active consumers detected
export async function publishToDlq(env: Env, message: unknown): Promise<void> {
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/lpush/${env.DLQ_KEY}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify([JSON.stringify(message)]),
  });

  if (!res.ok) {
    // DLQ write failed — log and drop. Better to lose the message than to block the request.
    console.error('[dlq] LPUSH failed', res.status);
  }
}
