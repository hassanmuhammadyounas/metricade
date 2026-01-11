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

export default function SyncShow() {
  const { result: record } = useShow({
    resource: "sync_runs",
  });

  return (
    <ShowView>
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Sync Run Details</CardTitle>
            <CardDescription>
              <div className="flex items-center gap-4">
                <Badge 
                  variant={
                    record?.status === "completed" ? "default" : 
                    record?.status === "failed" ? "destructive" : 
                    "secondary"
                  }
                >
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
              <h4 className="text-sm font-medium mb-2">Sync ID</h4>
              <p className="text-sm text-muted-foreground font-mono">{record?.sync_id || "-"}</p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Trigger Type</h4>
              <Badge variant="secondary">{record?.trigger_type || "-"}</Badge>
            </div>

            <Separator />

            <div className="grid grid-cols-3 gap-4">
              <div>
                <h4 className="text-sm font-medium mb-2">Records Queried</h4>
                <p className="text-2xl font-bold">{record?.records_queried?.toLocaleString() || "0"}</p>
              </div>
              <div>
                <h4 className="text-sm font-medium mb-2">Records Sent</h4>
                <p className="text-2xl font-bold text-green-600">{record?.records_sent?.toLocaleString() || "0"}</p>
              </div>
              <div>
                <h4 className="text-sm font-medium mb-2">Records Failed</h4>
                <p className="text-2xl font-bold text-red-600">{record?.records_failed?.toLocaleString() || "0"}</p>
              </div>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Duration</h4>
              <p className="text-sm text-muted-foreground">
                {record?.duration_ms ? `${(record.duration_ms / 1000).toFixed(2)} seconds` : "-"}
              </p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Started At</h4>
              <p className="text-sm text-muted-foreground">
                {record?.started_at ? new Date(record.started_at).toLocaleString() : "-"}
              </p>
            </div>

            <Separator />

            <div>
              <h4 className="text-sm font-medium mb-2">Completed At</h4>
              <p className="text-sm text-muted-foreground">
                {record?.completed_at ? new Date(record.completed_at).toLocaleString() : "In progress..."}
              </p>
            </div>

            {record?.error_message && (
              <>
                <Separator />
                <div>
                  <h4 className="text-sm font-medium mb-2 text-red-600">Error Message</h4>
                  <pre className="text-xs bg-red-50 dark:bg-red-950 p-3 rounded-md overflow-x-auto text-red-900 dark:text-red-100">
                    {record.error_message}
                  </pre>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </ShowView>
  );
}
