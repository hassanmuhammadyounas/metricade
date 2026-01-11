"use client";

import { Textarea } from "@/components/ui/textarea";
import { useForm } from "@refinedev/react-hook-form";
import { useRouter } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { CreateView } from "@/components/refine-ui/views/create-view";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

export default function DestinationCreate() {
  const router = useRouter();

  const {
    refineCore: { onFinish },
    ...form
  } = useForm({
    refineCoreProps: {
      resource: "google_ads_connections",
      redirect: "list",
    },
  });

  async function onSubmit(values: Record<string, string>) {
    await onFinish({
      ...values,
      status: "pending", // Will become 'active' after OAuth flow
    });
  }

  const callbackUrl = "http://localhost:3000/api/auth/google-ads/callback";

  return (
    <CreateView>
      <div className="space-y-6">
        {/* Setup Instructions */}
        <Card>
          <CardHeader>
            <CardTitle>Setup Instructions</CardTitle>
            <CardDescription>
              Follow these steps to create OAuth credentials for Google Ads API access
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <h4 className="font-semibold">Step 1: Create OAuth App in Google Cloud Console</h4>
              <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground">
                <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" className="underline">Google Cloud Console → APIs & Services → Credentials</a></li>
                <li>Click &quot;Create Credentials&quot; → &quot;OAuth client ID&quot;</li>
                <li>Select &quot;Web application&quot;</li>
                <li>Add this Authorized Redirect URI:</li>
              </ol>
              <Alert>
                <AlertDescription className="font-mono text-xs break-all">
                  {callbackUrl}
                </AlertDescription>
              </Alert>
              <p className="text-sm text-muted-foreground">Copy this URL exactly and paste it in the &quot;Authorized redirect URIs&quot; field</p>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold">Step 2: Get Your Customer ID</h4>
              <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground">
                <li>Go to your <a href="https://ads.google.com" target="_blank" rel="noopener noreferrer" className="underline">Google Ads account</a></li>
                <li>Look in the top-right corner for your Customer ID (format: 123-456-7890)</li>
              </ol>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold">Step 3: Fill the form below</h4>
              <p className="text-sm text-muted-foreground">
                After creating the OAuth app, you&apos;ll receive a Client ID and Client Secret. 
                Paste them below along with your Customer ID.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Form */}
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="name"
              rules={{ required: "Name is required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection Name</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value || ""}
                      placeholder="e.g., Main Google Ads Account"
                    />
                  </FormControl>
                  <FormDescription>
                    A friendly name to identify this connection
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="customer_id"
              rules={{ required: "Customer ID is required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Google Ads Customer ID</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value || ""}
                      placeholder="123-456-7890"
                    />
                  </FormControl>
                  <FormDescription>
                    Find this in the top-right corner of your Google Ads dashboard
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="client_id"
              rules={{ required: "Client ID is required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>OAuth Client ID</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value || ""}
                      placeholder="123456789-abc123.apps.googleusercontent.com"
                    />
                  </FormControl>
                  <FormDescription>
                    From Google Cloud Console → APIs & Services → Credentials
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="client_secret"
              rules={{ required: "Client Secret is required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>OAuth Client Secret</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value || ""}
                      type="password"
                      placeholder="GOCSPX-xxxxxxxxxxxxx"
                    />
                  </FormControl>
                  <FormDescription>
                    From the same OAuth credentials page (keep this secret!)
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Alert>
              <AlertDescription>
                <strong>Note:</strong> After creating this connection, you&apos;ll need to test it on the tRPC Test page 
                to complete the OAuth flow and get a refresh token. The connection will remain in &apos;pending&apos; status 
                until OAuth is completed.
              </AlertDescription>
            </Alert>

            <div className="flex gap-2">
              <Button
                type="submit"
                {...form.saveButtonProps}
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting ? "Creating..." : "Create Connection"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => router.back()}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </div>
    </CreateView>
  );
}
