import { z } from "zod";
import { createTRPCRouter, protectedProcedure } from "@/server/trpc";
import { BigQuery } from "@google-cloud/bigquery";
import { GoogleAdsApi } from "google-ads-api";

/**
 * Connections Router
 * Handles BigQuery and Google Ads connection testing
 */
export const connectionsRouter = createTRPCRouter({
  /**
   * Test BigQuery connection
   */
  testBigQuery: protectedProcedure
    .input(
      z.object({
        projectId: z.string(),
        serviceAccountKey: z.string(),
        datasetId: z.string().optional(),
      })
    )
    .mutation(async ({ input, ctx }) => {
      console.log("🔍 [testBigQuery] Starting connection test for project:", input.projectId);
      
      try {
        // Parse the service account key JSON
        let credentials;
        try {
          credentials = JSON.parse(input.serviceAccountKey);
          console.log("✅ [testBigQuery] Service account key parsed successfully");
        } catch (parseError) {
          console.error("❌ [testBigQuery] Failed to parse service account key");
          return {
            success: false,
            message: "Invalid service account key JSON format",
            error: "The service account key must be valid JSON",
          };
        }

        // Validate required fields in credentials
        if (!credentials.project_id || !credentials.private_key || !credentials.client_email) {
          console.error("❌ [testBigQuery] Missing required fields in service account key");
          return {
            success: false,
            message: "Invalid service account key structure",
            error: "Service account key must contain project_id, private_key, and client_email",
          };
        }

        // Create BigQuery client
        console.log("🔧 [testBigQuery] Creating BigQuery client...");
        const bigquery = new BigQuery({
          projectId: input.projectId,
          credentials: credentials,
        });

        // Test connection by listing datasets
        console.log("🔍 [testBigQuery] Attempting to list datasets...");
        const [datasets] = await bigquery.getDatasets();
        
        const datasetNames = datasets.map((dataset) => dataset.id || "unnamed");
        console.log(`✅ [testBigQuery] Successfully connected! Found ${datasetNames.length} dataset(s)`);

        return {
          success: true,
          message: `Successfully connected to BigQuery project: ${input.projectId}`,
          datasets: datasetNames,
          datasetCount: datasetNames.length,
          projectId: input.projectId,
          testedAt: new Date().toISOString(),
        };
      } catch (error: any) {
        console.error("❌ [testBigQuery] Connection failed:", error);

        // Handle specific BigQuery errors
        let errorMessage = "Failed to connect to BigQuery";
        let errorDetails = error.message || "Unknown error";

        if (error.code === 403) {
          errorMessage = "Permission denied";
          errorDetails = "The service account does not have permission to access this project";
        } else if (error.code === 404) {
          errorMessage = "Project not found";
          errorDetails = `BigQuery project '${input.projectId}' not found or inaccessible`;
        } else if (error.code === 401) {
          errorMessage = "Authentication failed";
          errorDetails = "Invalid service account credentials";
        } else if (error.message?.includes("ENOTFOUND")) {
          errorMessage = "Network error";
          errorDetails = "Unable to reach BigQuery API. Check your internet connection.";
        }

        return {
          success: false,
          message: errorMessage,
          error: errorDetails,
          errorCode: error.code,
        };
      }
    }),

  /**
   * Test Google Ads connection (OAuth version for MVP)
   */
  testGoogleAds: protectedProcedure
    .input(
      z.object({
        customerId: z.string(),
        clientId: z.string(),
        clientSecret: z.string(),
        refreshToken: z.string().optional(), // Optional - might not have it yet
      })
    )
    .mutation(async ({ input, ctx }) => {
      console.log("🔍 [testGoogleAds] Starting OAuth connection test for customer:", input.customerId);
      
      try {
        // If no refresh token yet, return instructions
        if (!input.refreshToken) {
          console.log("⚠️ [testGoogleAds] No refresh token - returning OAuth instructions");
          return {
            success: false,
            needsOAuth: true,
            message: "OAuth authentication required",
            error: "Please complete the OAuth flow to get a refresh token",
            oauthUrl: `https://accounts.google.com/o/oauth2/v2/auth?client_id=${input.clientId}&redirect_uri=${encodeURIComponent("http://localhost:3000/api/auth/google-ads/callback")}&response_type=code&scope=${encodeURIComponent("https://www.googleapis.com/auth/adwords")}&access_type=offline&prompt=consent`,
          };
        }

        // Initialize Google Ads API client with OAuth
        console.log("🔧 [testGoogleAds] Creating Google Ads API client with OAuth...");
        const client = new GoogleAdsApi({
          client_id: input.clientId,
          client_secret: input.clientSecret,
          developer_token: process.env.GOOGLE_ADS_DEVELOPER_TOKEN || "test-token", // For MVP, allow test
        });

        // Create customer client with OAuth refresh token
        const customer = client.Customer({
          customer_id: input.customerId.replace(/-/g, ""), // Remove dashes
          refresh_token: input.refreshToken,
        });

        // Test connection by listing conversion actions
        console.log("🔍 [testGoogleAds] Fetching conversion actions...");
        const conversionActions = await customer.query(`
          SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.type,
            conversion_action.status
          FROM conversion_action
          WHERE conversion_action.status != 'REMOVED'
          LIMIT 50
        `);

        console.log(`✅ [testGoogleAds] Successfully connected! Found ${conversionActions.length} conversion action(s)`);

        return {
          success: true,
          message: `Successfully connected to Google Ads customer: ${input.customerId}`,
          conversionActions: conversionActions.map((row: any) => ({
            id: row.conversion_action.id,
            name: row.conversion_action.name,
            type: row.conversion_action.type,
            status: row.conversion_action.status,
          })),
          conversionActionCount: conversionActions.length,
          customerId: input.customerId,
          testedAt: new Date().toISOString(),
        };
      } catch (error: any) {
        console.error("❌ [testGoogleAds] Connection failed:", error);

        // Handle specific Google Ads API errors
        let errorMessage = "Failed to connect to Google Ads";
        let errorDetails = error.message || "Unknown error";

        if (error.message?.includes("invalid_grant")) {
          errorMessage = "Invalid or expired refresh token";
          errorDetails = "Please re-authenticate using the OAuth flow";
        } else if (error.message?.includes("invalid_client")) {
          errorMessage = "Invalid OAuth credentials";
          errorDetails = "Check your Client ID and Client Secret";
        } else if (error.message?.includes("INVALID_CUSTOMER_ID")) {
          errorMessage = "Invalid customer ID";
          errorDetails = `Customer ID '${input.customerId}' is invalid or not accessible`;
        } else if (error.message?.includes("DEVELOPER_TOKEN")) {
          errorMessage = "Invalid developer token";
          errorDetails = "Contact support - developer token issue";
        }

        return {
          success: false,
          message: errorMessage,
          error: errorDetails,
          errorCode: error.code,
        };
      }
    }),

  /**
   * List user's BigQuery connections
   */
  listBigQueryConnections: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.supabase
      .from("bigquery_connections")
      .select("*")
      .eq("user_id", ctx.user.id)
      .order("created_at", { ascending: false });

    if (error) throw error;
    return data;
  }),

  /**
   * List user's Google Ads connections
   */
  listGoogleAdsConnections: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.supabase
      .from("google_ads_connections")
      .select("*")
      .eq("user_id", ctx.user.id)
      .order("created_at", { ascending: false });

    if (error) throw error;
    return data;
  }),
});
