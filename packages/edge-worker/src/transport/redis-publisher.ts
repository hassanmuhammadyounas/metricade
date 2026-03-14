import { Env } from '../index';
import { publishToDlq } from './dlq';

// XADD to metricade_stream:{org_id}. Falls back to DLQ only if XADD fails.
export async function publishToStream(env: Env, orgId: string, message: unknown): Promise<void> {
  const streamKey = `${env.STREAM_NAME}:${orgId}`;
  const body = JSON.stringify(message);
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify([
      ['XADD', streamKey, '*', 'payload', body],
    ]),
  });

  if (!res.ok) {
    const xaddResponse = await res.text();
    // XADD failed — fall back to DLQ. publishToDlq throws if DLQ also fails.
    await publishToDlq(env, orgId, message);
    // DLQ succeeded — data is safe, but we still surface the XADD failure so
    // ingest.ts can alert and decide the response code.
    throw new Error(`Redis XADD failed [${res.status}] (data saved to DLQ): ${xaddResponse}`);
  }
}
