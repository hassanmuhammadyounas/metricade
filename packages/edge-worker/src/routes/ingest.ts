import { Context } from 'hono';
import { Env } from '../index';
import { enrichIp } from '../enrichment/ip-enrichment';
import { enrichUa } from '../enrichment/ua-enrichment';
import { encodeTime } from '../enrichment/time-encoding';
import { publishToStream } from '../transport/redis-publisher';
import { INGEST_SHARED_SECRET_HEADER } from '../constants';

function sendToAxiom(env: Env, ctx: ExecutionContext, fields: Record<string, unknown>) {
  if (!env.AXIOM_TOKEN) return;
  ctx.waitUntil(
    fetch(`https://api.axiom.co/v1/datasets/${env.AXIOM_DATASET}/ingest`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.AXIOM_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([{ _time: new Date().toISOString(), service: 'edge-worker', ...fields }]),
    }),
  );
}

export async function ingest(c: Context<{ Bindings: Env }>) {
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

  const enriched = {
    trace_id: traceId,
    org_id: orgId,
    received_at: now,
    ip_meta: ipMeta,
    ua_meta: uaMeta,
    time_features: encodeTime(now),
    payload: body,
  };

  try {
    await publishToStream(c.env, orgId, enriched);
  } catch (err) {
    sendToAxiom(c.env, c.executionCtx, {
      event: 'ingest_error',
      trace_id: traceId,
      org_id: orgId,
      error: String(err),
    });
    return c.json({ error: 'internal_error' }, 500);
  }

  sendToAxiom(c.env, c.executionCtx, {
    event: 'ingest',
    trace_id: traceId,
    org_id: orgId,
    event_count: Array.isArray(body.events) ? (body.events as unknown[]).length : 0,
    ip_country: ipMeta.ip_country,
    ip_type: ipMeta.ip_type,
    ip_timezone: ipMeta.ip_timezone,
    device_type: uaMeta.device_type,
    browser_family: uaMeta.browser_family,
    is_webview: uaMeta.is_webview,
    duration_ms: Date.now() - t0,
  });

  return c.json({ ok: true, trace_id: traceId });
}
