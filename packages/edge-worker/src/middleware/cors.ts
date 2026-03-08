import { cors as honoCors } from 'hono/cors';

// Pixel runs on any customer website — reflect the request origin so the
// response is compatible with both credentialed and non-credentialed fetches.
// (Shopify and some other storefronts wrap fetch with credentials:'include'
// which the browser rejects against a wildcard Access-Control-Allow-Origin.)
export function cors() {
  return honoCors({
    origin: (origin) => origin || '*',
    allowMethods: ['POST', 'GET', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'x-trace-id', 'x-ingest-secret'],
    credentials: true,
    maxAge: 86400,
  });
}
