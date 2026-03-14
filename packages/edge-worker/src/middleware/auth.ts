import { createMiddleware } from 'hono/factory';
import { Env } from '../index';
import { ingestSharedSecretHeader } from '../constants';

export function auth() {
  return createMiddleware<{ Bindings: Env }>(async (c, next) => {
    const secret = c.req.header(ingestSharedSecretHeader);
    if (!secret || secret !== c.env.INGEST_SHARED_SECRET) {
      return c.json({ error: 'unauthorized' }, 401);
    }
    await next();
  });
}
