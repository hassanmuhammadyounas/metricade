import { Hono } from 'hono';
import { cors } from './middleware/cors';
import { auth } from './middleware/auth';
import { trace } from './middleware/trace';
import { ingest } from './routes/ingest';
import { health } from './routes/health';
import { dlqStatus } from './routes/dlq-status';

export type Env = {
  UPSTASH_REDIS_URL: string;
  UPSTASH_REDIS_TOKEN: string;
  INGEST_SHARED_SECRET: string;
  STREAM_NAME: string;
  DLQ_KEY: string;
  TRACE_HEADER: string;
  ENVIRONMENT: string;
  SLACK_WEBHOOK_URL: string;
};

export type Variables = {
  traceId: string;
};

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

// Global middleware
app.use('*', cors());
app.use('*', trace());

// Public routes — ingest handles its own auth (supports header + query param for sendBeacon)
app.post('/ingest', ingest);
app.get('/health', health);

// Internal routes — require shared secret
app.use('/dlq/*', auth());
app.get('/dlq/status', dlqStatus);

export default app;
