import { Context } from 'hono';
import { Env, Variables } from '../index';
import { enrichIp } from '../enrichment/ip-enrichment';
import { enrichUa } from '../enrichment/ua-enrichment';
import { encodeTime } from '../enrichment/time-encoding';
import { publishToStream } from '../transport/redis-publisher';
import { INGEST_SHARED_SECRET_HEADER } from '../constants';


export async function ingest(c: Context<{ Bindings: Env; Variables: Variables }>) {
  const t0 = Date.now();

  // ── Auth ──────────────────────────────────────────────────────────────────
  const secret = c.req.header(INGEST_SHARED_SECRET_HEADER) ?? c.req.query('s') ?? '';
  if (!secret || secret !== c.env.INGEST_SHARED_SECRET) {
    return c.json({ error: 'unauthorized' }, 401);
  }

  // ── Parse body ────────────────────────────────────────────────────────────
  let body: Record<string, unknown>;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: 'invalid_json' }, 400);
  }

  // ── Validate org_id ───────────────────────────────────────────────────────
  const orgId = typeof body.org_id === 'string' ? body.org_id : null;
  if (!orgId) {
    return c.json({ error: 'missing_org_id' }, 400);
  }

  // ── Enrich ────────────────────────────────────────────────────────────────
  const traceId = c.get('traceId') as string;
  const ip = c.req.header('x-forwarded-for')?.split(',')[0]?.trim() ?? 'unknown';
  const ua = c.req.header('user-agent') ?? '';
  const cf = c.req.raw.cf as { country?: string; asn?: number; asOrganization?: string; timezone?: string } | undefined;
  const now = Date.now();

  const ipMeta = enrichIp(ip, cf);
  const uaMeta = enrichUa(ua);

  const events = Array.isArray(body.events) ? body.events : [];
  const initEvent = events.find((e: unknown) => (e as Record<string, unknown>).event_type === 'init') as Record<string, unknown> | undefined;
  const browserTz: string = typeof initEvent?.browser_timezone === 'string' ? initEvent.browser_timezone : '';
  const timezoneMismatch = browserTz !== '' && browserTz !== ipMeta.ip_timezone;

  const originHeader = c.req.header('origin') ?? c.req.header('referer') ?? '';
  let hostname = '';
  try { hostname = originHeader ? new URL(originHeader).hostname : ''; } catch { hostname = ''; }

  const enriched = {
    trace_id: traceId,
    org_id: orgId,
    received_at: now,
    hostname,
    ip_meta: ipMeta,
    ua_meta: uaMeta,
    time_features: encodeTime(now),
    timezone_mismatch: timezoneMismatch,
    payload: body,
  };

  try {
    await publishToStream(c.env, orgId, enriched);
  } catch (err) {
    return c.json({ error: 'internal_error' }, 500);
  }

  return c.json({ ok: true, trace_id: traceId });
}
