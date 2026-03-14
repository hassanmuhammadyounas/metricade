import { Env } from '../index';
import { publishToDlq } from './dlq';

// Try XADD once. If it fails, attempt DLQ up to 3 times.
// Throws with 'data saved to DLQ' if DLQ succeeds (caller returns 200, no alert).
// Throws with 'DATA LOST' if all 3 DLQ attempts fail (caller returns 500 + Slack alert).
export async function publishToStream(env: Env, orgId: string, message: unknown): Promise<void> {
  const streamKey = `${env.STREAM_NAME}:${orgId}`;
  const body = JSON.stringify(message);

  const res = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify([['XADD', streamKey, '*', 'payload', body]]),
  });

  if (res.ok) return;

  const xaddError = await res.text();

  // XADD failed — attempt DLQ up to 3 times
  const DLQ_ATTEMPTS = 3;
  let lastDlqError = '';
  for (let attempt = 1; attempt <= DLQ_ATTEMPTS; attempt++) {
    try {
      await publishToDlq(env, orgId, message);
      // DLQ succeeded — data is safe, cron will drain it back to stream
      throw new Error(`XADD failed, data saved to DLQ after ${attempt} attempt(s): ${xaddError}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('data saved to DLQ')) throw err;
      lastDlqError = msg;
    }
  }

  throw new Error(
    `XADD failed and DLQ failed ${DLQ_ATTEMPTS} times — DATA LOST. XADD: ${xaddError} | DLQ: ${lastDlqError}`
  );
}
