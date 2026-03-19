import { Env } from '../index';

/**
 * Looks up the number of prior sessions for this client_id from Redis.
 * Key: metricade_client_sessions:{orgId}:{clientId}
 *
 * Uses a session-dedup key (SETNX metricade_new_sess:{orgId}:{sessionId}, no TTL)
 * to detect new sessions without double-counting repeated flushes.
 * INCR on client counter is fire-and-forget via ctx.waitUntil so it never
 * blocks the ingest response.
 *
 * Returns 0 on any Redis error (non-fatal).
 */
export async function enrichClientHistory(
  env: Env,
  orgId: string,
  clientId: string,
  sessionId: string,
  waitUntil: (p: Promise<unknown>) => void,
): Promise<number> {
  const sessKey   = `metricade_new_sess:${orgId}:${sessionId}`;
  const clientKey = `metricade_client_sessions:${orgId}:${clientId}`;

  let res: Response;
  try {
    res = await fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([
        ['GET', sessKey],    // stored prior count from first flush, or null if new session
        ['GET', clientKey],  // total sessions seen for this client
      ]),
    });
  } catch {
    return 0;
  }

  if (!res.ok) return 0;

  let results: Array<{ result: unknown }>;
  try {
    results = (await res.json()) as Array<{ result: unknown }>;
  } catch {
    return 0;
  }

  const storedCount = results[0]?.result;

  if (storedCount !== null && storedCount !== undefined) {
    // Repeat flush of same session — return the count frozen at first flush
    return parseInt(String(storedCount), 10) || 0;
  }

  // New session — prior count is the client's total before this session
  const priorCount = parseInt(String(results[1]?.result ?? '0'), 10) || 0;

  // Fire-and-forget: freeze prior count in sess key + increment client total
  waitUntil(
    fetch(`${env.UPSTASH_REDIS_URL}/pipeline`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([
        ['SET', sessKey, String(priorCount), 'NX'],
        ['INCR', clientKey],
      ]),
    }).catch(() => {}),
  );

  return priorCount;
}
