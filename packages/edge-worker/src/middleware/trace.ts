import { createMiddleware } from 'hono/factory';
import { Env, Variables } from '../index';
import { TRACE_HEADER } from '../constants';

export function trace() {
  return createMiddleware<{ Bindings: Env; Variables: Variables }>(async (c, next) => {
    // Use incoming trace_id if present, otherwise generate one
    const traceId = c.req.header(TRACE_HEADER) || crypto.randomUUID();
    c.set('traceId', traceId);
    c.header(TRACE_HEADER, traceId);
    await next();
  });
}
