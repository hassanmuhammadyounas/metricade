import type { Context } from 'hono';
import type { Env } from './index';
import { enrichIp } from './enrichment/ip-enrichment';
import { enrichUa } from './enrichment/ua-enrichment';

export async function ingest(c: Context<{ Bindings: Env }>): Promise<Response> {
  const env = c.env;

  // ── Auth (header for fetch; query param for sendBeacon) ──────────────────
  const secret = env.INGEST_SHARED_SECRET;
  const headerSecret = c.req.header('x-ingest-secret');
  const querySecret  = c.req.query('s');
  if (secret && headerSecret !== secret && querySecret !== secret) {
    return c.json({ error: 'Unauthorized' }, 401);
  }

  // ── Parse body ────────────────────────────────────────────────────────────
  let body: Record<string, unknown>;
  try {
    body = await c.req.json<Record<string, unknown>>();
  } catch {
    return c.json({ error: 'Invalid JSON' }, 400);
  }

  const org_id     = body.org_id     as string | undefined;
  const session_id = body.session_id as string | undefined;
  const client_id  = body.client_id  as string | undefined;
  const trace_id   = body.trace_id   as string | undefined;
  const hostname   = (body.hostname  as string | undefined) ?? extractHostname(c.req.header('origin') ?? c.req.header('referer') ?? '');
  const events     = body.events     as Record<string, unknown>[] | undefined;

  if (!org_id || !session_id || !client_id || !trace_id || !Array.isArray(events) || events.length === 0) {
    return c.json({ error: 'Missing required fields' }, 400);
  }

  // ── Enrichment ────────────────────────────────────────────────────────────
  const now = Date.now();
  const ip  = c.req.header('cf-connecting-ip') ?? '';
  const ua  = c.req.header('user-agent') ?? '';
  const cf  = (c.req.raw as Request & { cf?: { country?: string; asn?: number; asOrganization?: string; timezone?: string } }).cf;

  const ipMeta = enrichIp(ip, cf);
  const uaMeta = enrichUa(ua);

  // ── Build rows ────────────────────────────────────────────────────────────
  const sessionFields = {
    received_at: new Date(now).toISOString(),
    org_id,
    session_id,
    client_id,
    trace_id,
    hostname,
    browser_timezone:             (body.browser_timezone             as string  | null) ?? null,
    viewport_w_norm:              (body.viewport_w_norm              as number  | null) ?? null,
    viewport_h_norm:              (body.viewport_h_norm              as number  | null) ?? null,
    device_pixel_ratio:           (body.device_pixel_ratio           as number  | null) ?? null,
    time_to_first_interaction_ms: (body.time_to_first_interaction_ms as number  | null) ?? null,
    ip_address:  ip || null,
    ip_country:  ipMeta.ip_country,
    ip_asn:      ipMeta.ip_asn,
    ip_org:      ipMeta.ip_org,
    ip_type:     ipMeta.ip_type,
    ip_timezone: ipMeta.ip_timezone,
    user_agent:      ua || null,
    browser_family:  uaMeta.browser_family,
    browser_version: uaMeta.browser_version,
    os_family:       uaMeta.os_family,
    os_version:      uaMeta.os_version,
    device_type:     uaMeta.device_type,
    device_vendor:   uaMeta.device_vendor,
    is_webview:      uaMeta.is_webview,
  };

  const rows = events.map((e, i) => {
    const ts = typeof e.ts === 'number' ? e.ts : now;
    const d  = new Date(ts);
    return {
      ...sessionFields,
      event_seq:   i,
      event_ts:    d.toISOString(),
      hour_utc:    d.getUTCHours(),
      day_of_week: d.getUTCDay(),
      event_type:              e.event_type              ?? null,
      delta_ms:                e.delta_ms                ?? null,
      is_retry:                e.is_retry                ?? false,
      page_url:                e.page_url                ?? null,
      page_load_index:         e.page_load_index         ?? null,
      scroll_velocity_px_s:    e.scroll_velocity_px_s    ?? null,
      scroll_acceleration:     e.scroll_acceleration     ?? null,
      scroll_depth_pct:        e.scroll_depth_pct        ?? null,
      scroll_direction:        e.scroll_direction        ?? null,
      y_reversal:              e.y_reversal              ?? null,
      scroll_pause_duration_ms:e.scroll_pause_duration_ms?? null,
      patch_x:                 e.patch_x                 ?? null,
      patch_y:                 e.patch_y                 ?? null,
      tap_interval_ms:         e.tap_interval_ms         ?? null,
      tap_radius_x:            e.tap_radius_x            ?? null,
      tap_radius_y:            e.tap_radius_y            ?? null,
      tap_pressure:            e.tap_pressure            ?? null,
      dead_tap:                e.dead_tap                ?? null,
      long_press_duration_ms:  e.long_press_duration_ms  ?? null,
      backgrounded_ms:         e.backgrounded_ms         ?? null,
      active_ms:               e.active_ms               ?? null,
      idle_duration_ms:        e.idle_duration_ms        ?? null,
    };
  });

  // ── Insert into ClickHouse (fire-and-forget) ──────────────────────────────
  const ndjson = rows.map(r => JSON.stringify(r)).join('\n');
  const query  = 'INSERT INTO events FORMAT JSONEachRow';
  const auth   = btoa(`default:${env.CLICKHOUSE_PASSWORD}`);

  c.executionCtx.waitUntil(
    fetch(`${env.CLICKHOUSE_HOST}/?query=${encodeURIComponent(query)}`, {
      method: 'POST',
      headers: {
        'Authorization': `Basic ${auth}`,
        'Content-Type': 'application/octet-stream',
      },
      body: ndjson,
    }).catch(() => {}),
  );

  return c.json({ ok: true });
}

function extractHostname(url: string): string {
  try { return new URL(url).hostname; } catch { return url; }
}
