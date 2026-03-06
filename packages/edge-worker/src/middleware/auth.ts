import { createMiddleware } from 'hono/factory';
import { Env } from '../index';
import { INGEST_SHARED_SECRET_HEADER } from '../constants';

export function auth() {
  return createMiddleware<{ Bindings: Env }>(async (c, next) => {
    const secret = c.req.header(INGEST_SHARED_SECRET_HEADER);
    if (!secret || secret !== c.env.INGEST_SHARED_SECRET) {
      return c.json({ error: 'unauthorized' }, 401);
    }
    await next();
  });
}
