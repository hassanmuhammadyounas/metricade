import { Context } from 'hono';
import { Env } from '../index';

export async function health(c: Context<{ Bindings: Env }>) {
  let redisPing = false;
  try {
    const res = await fetch(`${c.env.UPSTASH_REDIS_URL}/ping`, {
      headers: { Authorization: `Bearer ${c.env.UPSTASH_REDIS_TOKEN}` },
    });
    redisPing = res.ok;
  } catch {
    redisPing = false;
  }

  return c.json({
    status: redisPing ? 'ok' : 'degraded',
    timestamp: new Date().toISOString(),
    redis_ping: redisPing,
    version: '1.0.0',
    environment: c.env.ENVIRONMENT,
  });
}
