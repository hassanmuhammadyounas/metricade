"use client";

import { Textarea } from "@/components/ui/textarea";
import { useForm } from "@refinedev/react-hook-form";
import { useRouter } from "next/navigation";

import { EditView } from "@/components/refine-ui/views/edit-view";
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

export default function SourceEdit() {
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
    await onFinish(values);
  }

  return (
    <EditView>
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
                  Your Google Cloud Platform project ID
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
                  Optional: Specify a default dataset for queries
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
                    placeholder='Paste the entire JSON file contents here...'
                    rows={12}
                    className="font-mono text-xs"
                  />
                </FormControl>
                <FormDescription>
                  The complete JSON key file from Google Cloud Console
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex gap-2">
            <Button
              type="submit"
              {...form.saveButtonProps}
              disabled={form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? "Saving..." : "Save Changes"}
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
    </EditView>
  );
}
