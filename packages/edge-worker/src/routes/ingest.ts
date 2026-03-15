import { Context } from 'hono';
import { Env, Variables } from '../index';
import { enrichIp } from '../enrichment/ip-enrichment';
import { enrichUa } from '../enrichment/ua-enrichment';
import { encodeTime } from '../enrichment/time-encoding';
import { enrichClientHistory } from '../enrichment/client-enrichment';
import { publishToStream } from '../transport/redis-publisher';
import { ingestSharedSecretHeader } from '../constants';
import { notifySlack } from '../alerts/slack';


export async function ingest(c: Context<{ Bindings: Env; Variables: Variables }>) {
  // ── Auth ──────────────────────────────────────────────────────────────────
  const secret = c.req.header(ingestSharedSecretHeader) ?? c.req.query('s') ?? '';
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
  const traceId = typeof body.trace_id === 'string' && body.trace_id ? body.trace_id : (c.get('traceId') as string);
  const ip = c.req.header('cf-connecting-ip') ?? c.req.header('x-forwarded-for')?.split(',')[0]?.trim() ?? 'unknown';
  const ua = c.req.header('user-agent') ?? '';
  const cf = c.req.raw.cf as { country?: string; asn?: number; asOrganization?: string; timezone?: string } | undefined;
  const now = Date.now();

  const ipMeta = enrichIp(ip, cf);
  const uaMeta = enrichUa(ua);

  const events = Array.isArray(body.events) ? body.events : [];
  const initEvent = events.find((e: unknown) => (e as Record<string, unknown>).event_type === 'page_view') as Record<string, unknown> | undefined;
  const browserTz: string = typeof body.browser_timezone === 'string' && body.browser_timezone
    ? body.browser_timezone
    : typeof initEvent?.browser_timezone === 'string' ? initEvent.browser_timezone : '';
  const timezoneMismatch = browserTz !== '' && browserTz !== ipMeta.ip_timezone;

  const originHeader = c.req.header('origin') ?? c.req.header('referer') ?? '';
  let hostname = '';
  try { hostname = originHeader ? new URL(originHeader).hostname : ''; } catch { hostname = ''; }

  const clientId  = typeof body.client_id  === 'string' ? body.client_id  : '';
  const sessionId = typeof body.session_id === 'string' ? body.session_id : '';
  const priorSessionCount = clientId && sessionId
    ? await enrichClientHistory(c.env, orgId, clientId, sessionId, c.executionCtx.waitUntil.bind(c.executionCtx))
    : 0;

  const enriched = {
    trace_id: traceId,
    org_id: orgId,
    received_at: now,
    hostname,
    ip_meta: ipMeta,
    ua_meta: uaMeta,
    time_features: encodeTime(now),
    timezone_mismatch: timezoneMismatch,
    prior_session_count: priorSessionCount,
    payload: body,
  };

  try {
    await publishToStream(c.env, orgId, enriched);
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    if (errMsg.includes('data saved to DLQ')) {
      // XADD failed but data is safe in DLQ — drain cron will recover it. No alert needed.
      return c.json({ ok: true, trace_id: traceId });
    }
    // Both XADD and DLQ failed after all retries — data is lost, alert immediately.
    console.error('[ingest] Redis publish failed completely:', errMsg);
    if (c.env.SLACK_WEBHOOK_URL) {
      const msg = `*Metricade ingest error — DATA LOST*\norg: ${orgId}\ntrace: ${traceId}\nerror: ${errMsg}`;
      c.executionCtx.waitUntil(notifySlack(c.env.SLACK_WEBHOOK_URL, msg));
    }
    return c.json({ error: 'internal_error' }, 500);
  }

  return c.json({ ok: true, trace_id: traceId });
}
