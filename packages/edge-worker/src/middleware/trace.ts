import { createMiddleware } from 'hono/factory';
import { Env, Variables } from '../index';
import { traceHeader } from '../constants';

export function trace() {
  return createMiddleware<{ Bindings: Env; Variables: Variables }>(async (c, next) => {
    // Use incoming trace_id if present, otherwise generate one
    const traceId = c.req.header(traceHeader) || crypto.randomUUID();
    c.set('traceId', traceId);
    c.header(traceHeader, traceId);
    await next();
  });
}
