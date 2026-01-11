"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { trpc } from "@/utils/trpc";

/**
 * Mask sensitive fields for display
 */
function maskSensitiveData(data: any): any {
  if (!data) return data;
  if (Array.isArray(data)) {
    return data.map(maskSensitiveData);
  }
  if (typeof data === "object") {
    const masked = { ...data };
    const sensitiveFields = [
      "service_account_key",
      "client_secret",
      "refresh_token",
      "access_token",
    ];
    for (const field of sensitiveFields) {
      if (masked[field]) {
        masked[field] = "***MASKED***";
      }
    }
    return masked;
  }
  return data;
}

/**
 * tRPC Test Page
 * Use this to test tRPC endpoints
 */
export default function TRPCTestPage() {
  const searchParams = useSearchParams();
  const [oauthMessage, setOauthMessage] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const { data: bqConnections, isLoading: bqLoading } =
    trpc.connections.listBigQueryConnections.useQuery();

  const { data: gaConnections, isLoading: gaLoading } =
    trpc.connections.listGoogleAdsConnections.useQuery();

  const [selectedBqId, setSelectedBqId] = useState<string>("");
  const [selectedGaId, setSelectedGaId] = useState<string>("");

  // Check for OAuth callback messages
  useEffect(() => {
    const success = searchParams.get("success");
    const error = searchParams.get("error");

    if (success) {
      setOauthMessage({ type: "success", message: success });
      // Clear URL params after showing message
      window.history.replaceState({}, "", "/trpc-test");
    } else if (error) {
      setOauthMessage({ type: "error", message: error });
      // Clear URL params after showing message
      window.history.replaceState({}, "", "/trpc-test");
    }
  }, [searchParams]);

  const testBigQuery = trpc.connections.testBigQuery.useMutation();
  const testGoogleAds = trpc.connections.testGoogleAds.useMutation();

  // Extract the actual array from the superjson wrapper
  // tRPC with superjson wraps data in {json: [...]}
  const bqConnectionsArray = Array.isArray(bqConnections) 
    ? bqConnections 
    : (bqConnections as any)?.json || [];
  const gaConnectionsArray = Array.isArray(gaConnections) 
    ? gaConnections 
    : (gaConnections as any)?.json || [];

  // Get selected connections
  const selectedBqConnection = bqConnectionsArray.find((conn: any) => conn.id === selectedBqId);
  const selectedGaConnection = gaConnectionsArray.find((conn: any) => conn.id === selectedGaId);

  // Check if selected connection has required fields
  const canTestBigQuery = !!(selectedBqConnection?.project_id && selectedBqConnection?.service_account_key);
  const canTestGoogleAds = !!(
    selectedGaConnection?.customer_id && 
    selectedGaConnection?.client_id && 
    selectedGaConnection?.client_secret
  );

  const handleTestBigQuery = () => {
    if (!selectedBqConnection || !canTestBigQuery) {
      console.error("❌ [handleTestBigQuery] Cannot test - missing connection or validation failed");
      console.log("selectedBqConnection:", selectedBqConnection);
      console.log("canTestBigQuery:", canTestBigQuery);
      return;
    }
    
    const payload = {
      projectId: selectedBqConnection.project_id,
      serviceAccountKey: selectedBqConnection.service_account_key,
      datasetId: selectedBqConnection.dataset_id || undefined,
    };
    
    console.log("🚀 [handleTestBigQuery] Sending mutation with payload:", {
      projectId: payload.projectId,
      hasServiceAccountKey: !!payload.serviceAccountKey,
      serviceAccountKeyLength: payload.serviceAccountKey?.length,
      datasetId: payload.datasetId,
    });
    
    testBigQuery.mutate(payload, {
      onSuccess: (data) => {
        console.log("✅ [handleTestBigQuery] Success:", data);
      },
      onError: (error) => {
        console.error("❌ [handleTestBigQuery] Error:", error);
      },
    });
  };

  const handleTestGoogleAds = () => {
    if (!selectedGaConnection || !canTestGoogleAds) {
      console.error("❌ [handleTestGoogleAds] Cannot test - missing connection or validation failed");
      console.log("selectedGaConnection:", selectedGaConnection);
      console.log("canTestGoogleAds:", canTestGoogleAds);
      return;
    }
    
    const payload = {
      customerId: selectedGaConnection.customer_id,
      clientId: selectedGaConnection.client_id,
      clientSecret: selectedGaConnection.client_secret,
      refreshToken: selectedGaConnection.refresh_token || undefined,
    };
    
    console.log("🚀 [handleTestGoogleAds] Sending mutation with payload:", {
      customerId: payload.customerId,
      hasClientId: !!payload.clientId,
      hasClientSecret: !!payload.clientSecret,
      hasRefreshToken: !!payload.refreshToken,
    });
    
    testGoogleAds.mutate(payload, {
      onSuccess: (data) => {
        console.log("✅ [handleTestGoogleAds] Success:", data);
        
        // If needs OAuth, open the URL
        if ((data as any).needsOAuth && (data as any).oauthUrl) {
          window.open((data as any).oauthUrl, "_blank");
        }
      },
      onError: (error) => {
        console.error("❌ [handleTestGoogleAds] Error:", error);
      },
    });
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <h1 className="text-3xl font-bold">tRPC Test Page</h1>

      {/* OAuth callback message */}
      {oauthMessage && (
        <Alert className={oauthMessage.type === "success" ? "border-green-500 bg-green-500/10" : "border-red-500 bg-red-500/10"}>
          <AlertDescription className={oauthMessage.type === "success" ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}>
            {oauthMessage.type === "success" ? "✓ " : "✗ "}
            {oauthMessage.message}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Left side - Test forms */}
        <div className="space-y-6">
          <Card>
        <CardHeader>
          <CardTitle>Test BigQuery Connection</CardTitle>
          <CardDescription>
            Select a connection to test. Required: project_id, service_account_key
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Select Connection</label>
            <Select value={selectedBqId} onValueChange={setSelectedBqId}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a BigQuery connection" />
              </SelectTrigger>
              <SelectContent>
                {bqConnectionsArray.length > 0 ? (
                  bqConnectionsArray.map((conn: any) => (
                    <SelectItem key={conn.id} value={conn.id}>
                      {conn.name} ({conn.project_id || "No project_id"})
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="none" disabled>
                    No connections available
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
            {selectedBqConnection && !canTestBigQuery && (
              <p className="text-sm text-destructive">
                Missing required fields: {!selectedBqConnection.project_id && "project_id"} {!selectedBqConnection.service_account_key && "service_account_key"}
              </p>
            )}
          </div>
          
          <Button
            onClick={handleTestBigQuery}
            disabled={!canTestBigQuery || testBigQuery.isPending}
          >
            {testBigQuery.isPending ? "Testing..." : "Test Connection"}
          </Button>
          
          {testBigQuery.data && (
            <div className="space-y-2">
              {testBigQuery.data.success ? (
                <div className="p-4 border border-green-500 bg-green-500/10 rounded">
                  <p className="font-semibold text-green-700 dark:text-green-400">
                    ✓ {testBigQuery.data.message}
                  </p>
                  {(testBigQuery.data as any).datasets && (testBigQuery.data as any).datasets.length > 0 && (
                    <div className="mt-2">
                      <p className="text-sm">
                        Found {(testBigQuery.data as any).datasetCount} dataset(s):
                      </p>
                      <ul className="list-disc list-inside text-sm mt-1">
                        {(testBigQuery.data as any).datasets.map((ds: string, i: number) => (
                          <li key={i}>{ds}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-4 border border-red-500 bg-red-500/10 rounded">
                  <p className="font-semibold text-red-700 dark:text-red-400">
                    ✗ {testBigQuery.data.message}
                  </p>
                  {(testBigQuery.data as any).error && (
                    <p className="text-sm mt-1 text-red-600 dark:text-red-300">
                      {(testBigQuery.data as any).error}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
          {testBigQuery.error && (
            <p className="text-destructive">{testBigQuery.error.message}</p>
          )}
        </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Test Google Ads Connection</CardTitle>
          <CardDescription>
            Select a connection to test. Required: customer_id, client_id, client_secret
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Select Connection</label>
            <Select value={selectedGaId} onValueChange={setSelectedGaId}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a Google Ads connection" />
              </SelectTrigger>
              <SelectContent>
                {gaConnectionsArray.length > 0 ? (
                  gaConnectionsArray.map((conn: any) => (
                    <SelectItem key={conn.id} value={conn.id}>
                      {conn.name} ({conn.customer_id || "No customer_id"})
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="none" disabled>
                    No connections available
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
            {selectedGaConnection && !canTestGoogleAds && (
              <p className="text-sm text-destructive">
                Missing required fields: {!selectedGaConnection.customer_id && "customer_id "} {!selectedGaConnection.client_id && "client_id "} {!selectedGaConnection.client_secret && "client_secret"}
              </p>
            )}
          </div>
          
          <Button
            onClick={handleTestGoogleAds}
            disabled={!canTestGoogleAds || testGoogleAds.isPending}
          >
            {testGoogleAds.isPending ? "Testing..." : "Test Connection"}
          </Button>
          
          {testGoogleAds.data && (
            <div className="space-y-2">
              {testGoogleAds.data.success ? (
                <div className="p-4 border border-green-500 bg-green-500/10 rounded">
                  <p className="font-semibold text-green-700 dark:text-green-400">
                    ✓ {testGoogleAds.data.message}
                  </p>
                  {(testGoogleAds.data as any).conversionActions && (
                    <div className="mt-2">
                      <p className="text-sm">Conversion Actions:</p>
                      <ul className="list-disc list-inside text-sm mt-1">
                        {(testGoogleAds.data as any).conversionActions.map((action: any, i: number) => (
                          <li key={i}>
                            {action.name} (ID: {action.id})
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-4 border border-red-500 bg-red-500/10 rounded">
                  <p className="font-semibold text-red-700 dark:text-red-400">
                    ✗ {testGoogleAds.data.message}
                  </p>
                  {(testGoogleAds.data as any).error && (
                    <p className="text-sm mt-1 text-red-600 dark:text-red-300">
                      {(testGoogleAds.data as any).error}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
          {testGoogleAds.error && (
            <p className="text-destructive">{testGoogleAds.error.message}</p>
          )}
        </CardContent>
          </Card>
        </div>

        {/* Right side - Connection data */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>BigQuery Connections</CardTitle>
              <CardDescription>Available connections from database</CardDescription>
            </CardHeader>
            <CardContent>
              {bqLoading ? (
                <p>Loading...</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">
                    Total: {bqConnectionsArray.length} connection(s)
                  </p>
                  <pre className="bg-muted p-4 rounded overflow-auto max-h-96 text-xs">
                    {JSON.stringify(maskSensitiveData(bqConnectionsArray), null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Google Ads Connections</CardTitle>
              <CardDescription>Available connections from database</CardDescription>
            </CardHeader>
            <CardContent>
              {gaLoading ? (
                <p>Loading...</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">
                    Total: {gaConnectionsArray.length} connection(s)
                  </p>
                  <pre className="bg-muted p-4 rounded overflow-auto max-h-96 text-xs">
                    {JSON.stringify(maskSensitiveData(gaConnectionsArray), null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
