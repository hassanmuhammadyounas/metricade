import { Context } from 'hono';
import { Env } from '../index';

export async function dlqStatus(c: Context<{ Bindings: Env }>) {
  // LLEN behavioral_dlq
  const lenRes = await fetch(`${c.env.UPSTASH_REDIS_URL}/llen/${c.env.DLQ_KEY}`, {
    headers: { Authorization: `Bearer ${c.env.UPSTASH_REDIS_TOKEN}` },
  });
  const { result: count } = await lenRes.json<{ result: number }>();

  // LINDEX behavioral_dlq 0 — oldest message
  let oldestAgeMs: number | null = null;
  if (count > 0) {
    const oldestRes = await fetch(`${c.env.UPSTASH_REDIS_URL}/lindex/${c.env.DLQ_KEY}/0`, {
      headers: { Authorization: `Bearer ${c.env.UPSTASH_REDIS_TOKEN}` },
    });
    const { result: oldest } = await oldestRes.json<{ result: string }>();
    try {
      const msg = JSON.parse(oldest);
      if (msg.received_at) oldestAgeMs = Date.now() - msg.received_at;
    } catch {
      // malformed message
    }
  }

  return c.json({ dlq_count: count, oldest_message_age_ms: oldestAgeMs });
}
