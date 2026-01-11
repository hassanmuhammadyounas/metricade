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

export default function SourceShow() {
  const { result: record } = useShow({
    resource: "bigquery_connections",
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
              <h4 className="text-sm font-medium mb-2">Project ID</h4>
              <p className="text-sm text-muted-foreground">{record?.project_id || "-"}</p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Dataset ID</h4>
              <p className="text-sm text-muted-foreground">{record?.dataset_id || "-"}</p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Last Tested</h4>
              <p className="text-sm text-muted-foreground">
                {record?.last_tested_at
                  ? new Date(record.last_tested_at).toLocaleString()
                  : "Never"}
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
