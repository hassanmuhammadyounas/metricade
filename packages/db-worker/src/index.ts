import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { ingest } from './ingest';

export type Env = {
  CLICKHOUSE_HOST: string;
  CLICKHOUSE_PASSWORD: string;
  INGEST_SHARED_SECRET: string;
};

const app = new Hono<{ Bindings: Env }>();

app.use('*', cors());

app.post('/ingest', ingest);
app.get('/health', (c) => c.json({ ok: true }));

export default { fetch: app.fetch.bind(app) };
