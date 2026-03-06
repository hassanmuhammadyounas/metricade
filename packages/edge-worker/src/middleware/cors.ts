import { cors as honoCors } from 'hono/cors';

// Pixel runs on any customer website — allow all origins
export function cors() {
  return honoCors({
    origin: '*',
    allowMethods: ['POST', 'GET', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'x-trace-id', 'x-ingest-secret'],
    maxAge: 86400,
  });
}
