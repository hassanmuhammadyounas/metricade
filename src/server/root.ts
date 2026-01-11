import { createTRPCRouter } from "@/server/trpc";
import { connectionsRouter } from "./routers/connections";
import { syncsRouter } from "./routers/syncs";

/**
 * Main tRPC router
 * Add all sub-routers here
 */
export const appRouter = createTRPCRouter({
  connections: connectionsRouter,
  syncs: syncsRouter,
});

export type AppRouter = typeof appRouter;
