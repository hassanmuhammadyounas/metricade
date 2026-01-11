"use client";

import { useShow } from "@refinedev/core";

import { ShowView } from "@/components/refine-ui/views/show-view";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function ConnectionShow() {
  const { result: record } = useShow({
    resource: "syncs",
  });

  return (
    <ShowView>
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{record?.name}</CardTitle>
            <CardDescription>
              <div className="flex items-center gap-4">
                <Badge variant={record?.status === "active" ? "default" : "secondary"}>
                  {record?.status}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  ID: {record?.id}
                </span>
              </div>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h4 className="text-sm font-medium mb-2">Query</h4>
              <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
                {record?.query || "-"}
              </pre>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Field Mappings</h4>
              <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
                {record?.field_mappings ? JSON.stringify(record.field_mappings, null, 2) : "-"}
              </pre>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Schedule</h4>
              <p className="text-sm text-muted-foreground">{record?.schedule || "Manual"}</p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Last Run</h4>
              <p className="text-sm text-muted-foreground">
                {record?.last_run_at
                  ? new Date(record.last_run_at).toLocaleString()
                  : "Never"}
              </p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Next Run</h4>
              <p className="text-sm text-muted-foreground">
                {record?.next_run_at
                  ? new Date(record.next_run_at).toLocaleString()
                  : "Not scheduled"}
              </p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Created At</h4>
              <p className="text-sm text-muted-foreground">
                {record?.created_at
                  ? new Date(record.created_at).toLocaleDateString()
                  : "-"}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </ShowView>
  );
}
