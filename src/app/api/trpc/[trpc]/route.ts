import { fetchRequestHandler } from "@trpc/server/adapters/fetch";
import { appRouter } from "@/server/root";
import { createTRPCContext } from "@/server/trpc";

/**
 * tRPC API handler for Next.js App Router
 */
const handler = async (req: Request) => {
  // Log incoming request
  console.log("🔍 [tRPC Handler] Incoming request:", {
    method: req.method,
    url: req.url,
    headers: Object.fromEntries(req.headers.entries()),
  });

  // For POST, log the body
  if (req.method === "POST") {
    const clonedReq = req.clone();
    const body = await clonedReq.text();
    console.log("🔍 [tRPC Handler] Request body:", body);
  }

  return fetchRequestHandler({
    endpoint: "/api/trpc",
    req,
    router: appRouter,
    createContext: createTRPCContext,
    onError:
      process.env.NODE_ENV === "development"
        ? ({ path, error }) => {
            console.error(
              `❌ tRPC failed on ${path ?? "<no-path>"}:`,
              JSON.stringify(error, null, 2)
            );
          }
        : undefined,
  });
};

export { handler as GET, handler as POST };
