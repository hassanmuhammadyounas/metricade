import { z } from "zod";
import { createTRPCRouter, protectedProcedure } from "@/server/trpc";

/**
 * Syncs Router
 * Handles sync operations and job management
 */
export const syncsRouter = createTRPCRouter({
  /**
   * Manually trigger a sync
   */
  triggerSync: protectedProcedure
    .input(
      z.object({
        syncId: z.string().uuid(),
      })
    )
    .mutation(async ({ input, ctx }) => {
      // TODO: Create Bull job and trigger sync
      // For now, return mock response
      return {
        success: true,
        jobId: "mock-job-id-123",
        message: "Sync triggered successfully",
      };
    }),

  /**
   * Get sync status
   */
  getSyncStatus: protectedProcedure
    .input(
      z.object({
        syncId: z.string().uuid(),
      })
    )
    .query(async ({ input, ctx }) => {
      const { data, error } = await ctx.supabase
        .from("syncs")
        .select("*")
        .eq("id", input.syncId)
        .eq("user_id", ctx.user.id)
        .single();

      if (error) throw error;
      return data;
    }),

  /**
   * List sync runs for a sync
   */
  listSyncRuns: protectedProcedure
    .input(
      z.object({
        syncId: z.string().uuid(),
        limit: z.number().optional().default(10),
      })
    )
    .query(async ({ input, ctx }) => {
      // First verify the sync belongs to the user
      const { data: sync, error: syncError } = await ctx.supabase
        .from("syncs")
        .select("id")
        .eq("id", input.syncId)
        .eq("user_id", ctx.user.id)
        .single();

      if (syncError) throw syncError;

      // Get sync runs
      const { data, error } = await ctx.supabase
        .from("sync_runs")
        .select("*")
        .eq("sync_id", input.syncId)
        .order("created_at", { ascending: false })
        .limit(input.limit);

      if (error) throw error;
      return data;
    }),

  /**
   * Preview BigQuery data
   */
  previewBigQueryData: protectedProcedure
    .input(
      z.object({
        connectionId: z.string().uuid(),
        query: z.string(),
      })
    )
    .mutation(async ({ input, ctx }) => {
      // TODO: Execute BigQuery query and return sample data
      // For now, return mock response
      return {
        success: true,
        rows: [
          {
            gclid: "abc123",
            conversion_date_time: "2026-01-10 12:00:00",
            conversion_value: 100,
            email: "test@example.com",
          },
        ],
        schema: [
          { name: "gclid", type: "STRING" },
          { name: "conversion_date_time", type: "TIMESTAMP" },
          { name: "conversion_value", type: "FLOAT" },
          { name: "email", type: "STRING" },
        ],
      };
    }),
});
