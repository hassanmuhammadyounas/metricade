import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/utils/supabase/server";

/**
 * OAuth Callback Handler for Google Ads
 * Exchanges authorization code for refresh token
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const error = searchParams.get("error");

  console.log("🔍 [OAuth Callback] Received request:", {
    hasCode: !!code,
    error: error,
  });

  // Handle OAuth errors
  if (error) {
    console.error("❌ [OAuth Callback] OAuth error:", error);
    return NextResponse.redirect(
      new URL(
        `/trpc-test?error=${encodeURIComponent(`OAuth failed: ${error}`)}`,
        request.url
      )
    );
  }

  // No authorization code
  if (!code) {
    console.error("❌ [OAuth Callback] No authorization code received");
    return NextResponse.redirect(
      new URL(
        `/trpc-test?error=${encodeURIComponent("No authorization code received")}`,
        request.url
      )
    );
  }

  try {
    // Get the connection ID from state (if we implement it later)
    // For now, we'll need to find the most recent pending connection
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      console.error("❌ [OAuth Callback] User not authenticated");
      return NextResponse.redirect(
        new URL(
          `/login?error=${encodeURIComponent("Please log in first")}`,
          request.url
        )
      );
    }

    // Get the most recent pending Google Ads connection for this user
    const { data: connections, error: fetchError } = await supabase
      .from("google_ads_connections")
      .select("*")
      .eq("user_id", user.id)
      .eq("status", "pending")
      .order("created_at", { ascending: false })
      .limit(1);

    if (fetchError || !connections || connections.length === 0) {
      console.error("❌ [OAuth Callback] No pending connection found:", fetchError);
      return NextResponse.redirect(
        new URL(
          `/trpc-test?error=${encodeURIComponent("No pending connection found. Please create a connection first.")}`,
          request.url
        )
      );
    }

    const connection = connections[0];
    console.log("✅ [OAuth Callback] Found connection:", connection.id);

    // Exchange authorization code for tokens
    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        code: code,
        client_id: connection.client_id,
        client_secret: connection.client_secret,
        redirect_uri: `${request.nextUrl.origin}/api/auth/google-ads/callback`,
        grant_type: "authorization_code",
      }),
    });

    if (!tokenResponse.ok) {
      const errorData = await tokenResponse.json();
      console.error("❌ [OAuth Callback] Token exchange failed:", errorData);
      return NextResponse.redirect(
        new URL(
          `/trpc-test?error=${encodeURIComponent(`Token exchange failed: ${errorData.error_description || errorData.error}`)}`,
          request.url
        )
      );
    }

    const tokens = await tokenResponse.json();
    console.log("✅ [OAuth Callback] Received tokens:", {
      hasRefreshToken: !!tokens.refresh_token,
      hasAccessToken: !!tokens.access_token,
      expiresIn: tokens.expires_in,
    });

    // Calculate token expiry
    const expiresAt = new Date();
    expiresAt.setSeconds(expiresAt.getSeconds() + tokens.expires_in);

    // Update the connection with tokens
    const { error: updateError } = await supabase
      .from("google_ads_connections")
      .update({
        refresh_token: tokens.refresh_token,
        access_token: tokens.access_token,
        token_expires_at: expiresAt.toISOString(),
        status: "active",
        last_tested_at: new Date().toISOString(),
      })
      .eq("id", connection.id);

    if (updateError) {
      console.error("❌ [OAuth Callback] Failed to update connection:", updateError);
      return NextResponse.redirect(
        new URL(
          `/trpc-test?error=${encodeURIComponent("Failed to save tokens to database")}`,
          request.url
        )
      );
    }

    console.log("✅ [OAuth Callback] Successfully updated connection with tokens");

    // Redirect back to test page with success message
    return NextResponse.redirect(
      new URL(
        `/trpc-test?success=${encodeURIComponent("OAuth completed successfully! You can now test the connection.")}`,
        request.url
      )
    );
  } catch (error: any) {
    console.error("❌ [OAuth Callback] Unexpected error:", error);
    return NextResponse.redirect(
      new URL(
        `/trpc-test?error=${encodeURIComponent(`Unexpected error: ${error.message}`)}`,
        request.url
      )
    );
  }
}
