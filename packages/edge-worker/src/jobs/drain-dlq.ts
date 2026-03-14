import { Env } from '../index';

// Drain all metricade_dlq:{org_id} lists back into their streams.
// Runs on a cron schedule — edge worker owns all DLQ responsibility.
export async function drainDlqs(env: Env): Promise<void> {
  const headers = {
    Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
    'Content-Type': 'application/json',
  };

  // 1. Find all DLQ keys
  const scanRes = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
    method: 'POST',
    headers,
    body: JSON.stringify([['SCAN', '0', 'MATCH', `${env.DLQ_KEY}:*`, 'COUNT', '100']]),
  });
  if (!scanRes.ok) return;

  const scanData = await scanRes.json() as Array<{ result: [string, string[]] }>;
  const dlqKeys: string[] = scanData[0]?.result?.[1] ?? [];
  if (dlqKeys.length === 0) return;

  for (const dlqKey of dlqKeys) {
    const orgId = dlqKey.slice(env.DLQ_KEY.length + 1);
    const streamKey = `${env.STREAM_NAME}:${orgId}`;

    // 2. RPOP up to 100 items per DLQ key in one pipeline
    const rpopRes = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
      method: 'POST',
      headers,
      body: JSON.stringify(Array.from({ length: 100 }, () => ['RPOP', dlqKey])),
    });
    if (!rpopRes.ok) continue;

    const rpopData = await rpopRes.json() as Array<{ result: string | null }>;
    const items = rpopData.map(r => r.result).filter((r): r is string => r !== null);
    if (items.length === 0) continue;

    // 3. XADD each recovered item back into the stream
    await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
      method: 'POST',
      headers,
      body: JSON.stringify(items.map(item => ['XADD', streamKey, '*', 'payload', item])),
    });
  }
}
