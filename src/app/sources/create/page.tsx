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

export default function SourceCreate() {
  const router = useRouter();

  const {
    refineCore: { onFinish },
    ...form
  } = useForm({
    refineCoreProps: {
      resource: "bigquery_connections",
      redirect: "list",
    },
  });

  async function onSubmit(values: Record<string, string>) {
    await onFinish({
      ...values,
      status: "testing",
    });
  }

  return (
    <CreateView>
      <div className="space-y-6">
        {/* Setup Instructions */}
        <Card>
          <CardHeader>
            <CardTitle>Setup Instructions</CardTitle>
            <CardDescription>
              Follow these steps to create a service account and connect to your BigQuery project
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <h4 className="font-semibold">Step 1: Create a Service Account in Google Cloud Console</h4>
              <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground ml-2">
                <li>Go to <a href="https://console.cloud.google.com/iam-admin/serviceaccounts" target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">Google Cloud Console → IAM & Admin → Service Accounts</a></li>
                <li>Select your project or create a new one</li>
                <li>Click &quot;Create Service Account&quot;</li>
                <li>Enter a name (e.g., &quot;metricade-bigquery-access&quot;)</li>
                <li>Click &quot;Create and Continue&quot;</li>
              </ol>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold">Step 2: Grant BigQuery Permissions</h4>
              <p className="text-sm text-muted-foreground ml-2">Assign these roles to the service account:</p>
              <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground ml-4">
                <li><code className="bg-muted px-1 py-0.5 rounded">BigQuery Data Viewer</code> - Read access to query data</li>
                <li><code className="bg-muted px-1 py-0.5 rounded">BigQuery Job User</code> - Run queries</li>
                <li><code className="bg-muted px-1 py-0.5 rounded">BigQuery Metadata Viewer</code> (Optional) - List datasets and tables</li>
              </ul>
              <p className="text-xs text-muted-foreground ml-2 mt-2">
                Note: For read-only access, these permissions are sufficient. For write access (if needed later), 
                add <code className="bg-muted px-1 py-0.5 rounded">BigQuery Data Editor</code>
              </p>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold">Step 3: Create and Download Service Account Key</h4>
              <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground ml-2">
                <li>Click on the service account you just created</li>
                <li>Go to the &quot;Keys&quot; tab</li>
                <li>Click &quot;Add Key&quot; → &quot;Create new key&quot;</li>
                <li>Select &quot;JSON&quot; format</li>
                <li>Click &quot;Create&quot; - a JSON file will download automatically</li>
              </ol>
              <Alert className="mt-2">
                <AlertDescription className="text-xs">
                  <strong>Security Warning:</strong> This JSON file contains credentials that grant access to your BigQuery data. 
                  Keep it secure and never commit it to version control.
                </AlertDescription>
              </Alert>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold">Step 4: Get Your Project ID</h4>
              <p className="text-sm text-muted-foreground ml-2">
                Your Project ID can be found:
              </p>
              <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground ml-4">
                <li>In the downloaded JSON file (look for the <code className="bg-muted px-1 py-0.5 rounded">project_id</code> field)</li>
                <li>At the top of Google Cloud Console (next to the project name)</li>
                <li>Format example: <code className="bg-muted px-1 py-0.5 rounded">my-project-123456</code></li>
              </ul>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold">Step 5: Fill the Form Below</h4>
              <p className="text-sm text-muted-foreground ml-2">
                Copy the entire contents of the downloaded JSON file and paste it in the &quot;Service Account Key&quot; field below.
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
                      placeholder="e.g., Production BigQuery"
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
              name="project_id"
              rules={{ required: "Project ID is required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>GCP Project ID</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value || ""}
                      placeholder="my-project-123456"
                    />
                  </FormControl>
                  <FormDescription>
                    Find this in your Google Cloud Console or in the downloaded JSON file
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="dataset_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Default Dataset ID (Optional)</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value || ""}
                      placeholder="my_dataset"
                    />
                  </FormControl>
                  <FormDescription>
                    Optional: Specify a default dataset. You can still query other datasets by using fully-qualified table names
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="service_account_key"
              rules={{ required: "Service Account Key is required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Service Account Key (JSON)</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      value={field.value || ""}
                      placeholder='Paste the entire JSON file contents here, e.g.:
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "your-sa@project.iam.gserviceaccount.com",
  ...
}'
                      rows={12}
                      className="font-mono text-xs"
                    />
                  </FormControl>
                  <FormDescription>
                    Paste the complete JSON key file downloaded from Google Cloud Console
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Alert>
              <AlertDescription>
                <strong>Next Step:</strong> After creating this connection, go to the &quot;tRPC Test&quot; page 
                to verify the connection and see which datasets you have access to. The connection will remain in 
                &apos;testing&apos; status until successfully tested.
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
