"use client";

import { useTable } from "@refinedev/react-table";
import { createColumnHelper } from "@tanstack/react-table";
import React from "react";

import { ShowButton } from "@/components/refine-ui/buttons/show";
import { DataTable } from "@/components/refine-ui/data-table/data-table";
import { ListView, ListViewHeader } from "@/components/refine-ui/views/list-view";
import { Badge } from "@/components/ui/badge";

type SyncRun = {
  id: string;
  sync_id: string;
  status: string;
  trigger_type: string;
  records_sent: number | null;
  records_failed: number | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
};

export default function SyncsList() {
  const columns = React.useMemo(() => {
    const columnHelper = createColumnHelper<SyncRun>();

    return [
      columnHelper.accessor("sync_id", {
        id: "sync_id",
        header: "Sync ID",
        enableSorting: false,
        cell: ({ getValue }) => {
          const id = getValue();
          return <span className="text-xs font-mono">{id?.slice(0, 8)}...</span>;
        },
      }),
      columnHelper.accessor("status", {
        id: "status",
        header: "Status",
        enableSorting: true,
        cell: ({ getValue }) => {
          const status = getValue();
          const variant = 
            status === "completed" ? "default" : 
            status === "failed" ? "destructive" : 
            status === "running" ? "outline" : 
            "secondary";
          return <Badge variant={variant}>{status}</Badge>;
        },
      }),
      columnHelper.accessor("trigger_type", {
        id: "trigger_type",
        header: "Trigger",
        enableSorting: true,
        cell: ({ getValue }) => {
          const type = getValue();
          return <Badge variant="secondary">{type}</Badge>;
        },
      }),
      columnHelper.accessor("records_sent", {
        id: "records_sent",
        header: "Sent",
        enableSorting: true,
        cell: ({ getValue }) => getValue()?.toLocaleString() || "0",
      }),
      columnHelper.accessor("records_failed", {
        id: "records_failed",
        header: "Failed",
        enableSorting: true,
        cell: ({ getValue }) => getValue()?.toLocaleString() || "0",
      }),
      columnHelper.accessor("duration_ms", {
        id: "duration_ms",
        header: "Duration",
        enableSorting: true,
        cell: ({ getValue }) => {
          const ms = getValue();
          if (!ms) return "-";
          const seconds = (ms / 1000).toFixed(2);
          return `${seconds}s`;
        },
      }),
      columnHelper.accessor("started_at", {
        id: "started_at",
        header: "Started At",
        enableSorting: true,
        cell: ({ getValue }) => {
          const date = getValue();
          return date ? new Date(date).toLocaleString() : "-";
        },
      }),
      columnHelper.display({
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <div className="flex gap-2">
            <ShowButton recordItemId={row.original.id} size="sm" />
          </div>
        ),
        enableSorting: false,
        size: 100,
      }),
    ];
  }, []);

  const table = useTable({
    columns,
    refineCoreProps: {
      syncWithLocation: true,
      resource: "sync_runs",
    },
  });

  return (
    <ListView>
      <ListViewHeader canCreate={false} />
      <DataTable table={table} />
    </ListView>
  );
}
