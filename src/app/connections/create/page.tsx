"use client";

import { Textarea } from "@/components/ui/textarea";
import { useForm } from "@refinedev/react-hook-form";
import { useRouter } from "next/navigation";

import { CreateView } from "@/components/refine-ui/views/create-view";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

export default function ConnectionCreate() {
  const router = useRouter();

  const {
    refineCore: { onFinish },
    ...form
  } = useForm({
    refineCoreProps: {
      resource: "syncs",
    },
  });

  function onSubmit(values: Record<string, any>) {
    // Convert field_mappings string to JSON if it's a string
    const payload = {
      ...values,
      status: "draft",
      field_mappings: values.field_mappings ? JSON.parse(values.field_mappings) : {},
    };
    onFinish(payload);
  }

  return (
    <CreateView>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
          <FormField
            control={form.control}
            name="name"
            rules={{ required: "Name is required" }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>Sync Name</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value || ""}
                    placeholder="e.g., Daily Offline Conversions"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="bigquery_connection_id"
            rules={{ required: "BigQuery connection is required" }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>BigQuery Connection ID</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value || ""}
                    placeholder="Source connection UUID"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="google_ads_connection_id"
            rules={{ required: "Google Ads connection is required" }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>Google Ads Connection ID</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value || ""}
                    placeholder="Destination connection UUID"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="query"
            rules={{ required: "Query is required" }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>BigQuery SQL Query</FormLabel>
                <FormControl>
                  <Textarea
                    {...field}
                    value={field.value || ""}
                    placeholder="SELECT * FROM my_dataset.conversions"
                    rows={5}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="field_mappings"
            rules={{ required: "Field mappings are required" }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>Field Mappings (JSON)</FormLabel>
                <FormDescription>
                  Map BigQuery columns to Google Ads fields
                </FormDescription>
                <FormControl>
                  <Textarea
                    {...field}
                    value={field.value || ""}
                    placeholder='{"email": "email", "conversion_value": "conversion_value"}'
                    rows={5}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="schedule"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Schedule (Cron Expression - Optional)</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value || ""}
                    placeholder="0 2 * * * (2 AM daily)"
                  />
                </FormControl>
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
    </CreateView>
  );
}
