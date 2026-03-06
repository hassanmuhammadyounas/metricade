import { cors as honoCors } from 'hono/cors';

// List allowed origins — add your production and staging domains here
const ALLOWED_ORIGINS = [
  'https://your-domain.com',
  'https://staging.your-domain.com',
];

export function cors() {
  return honoCors({
    origin: ALLOWED_ORIGINS,
    allowMethods: ['POST', 'GET', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'x-trace-id'],
    maxAge: 86400,
  });
}
