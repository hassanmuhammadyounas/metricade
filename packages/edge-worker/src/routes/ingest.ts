import { Context } from 'hono';
import { Env } from '../index';
import { enrichIp } from '../enrichment/ip-enrichment';
import { enrichUa } from '../enrichment/ua-enrichment';
import { encodeTime } from '../enrichment/time-encoding';
import { publishToStream } from '../transport/redis-publisher';

export async function ingest(c: Context<{ Bindings: Env }>) {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: 'invalid_json' }, 400);
  }

  const traceId = c.get('traceId') as string;
  const ip = c.req.header('x-forwarded-for')?.split(',')[0]?.trim() ?? 'unknown';
  const ua = c.req.header('user-agent') ?? '';
  const now = Date.now();

  const enriched = {
    trace_id: traceId,
    received_at: now,
    ip_meta: await enrichIp(ip),
    ua_meta: enrichUa(ua),
    time_features: encodeTime(now),
    payload: body,
  };

  await publishToStream(c.env, enriched);

  return c.json({ ok: true, trace_id: traceId });
}
