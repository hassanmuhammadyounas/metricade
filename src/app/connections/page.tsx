"use client";

import { useTable } from "@refinedev/react-table";
import { createColumnHelper } from "@tanstack/react-table";
import React from "react";

import { DeleteButton } from "@/components/refine-ui/buttons/delete";
import { EditButton } from "@/components/refine-ui/buttons/edit";
import { ShowButton } from "@/components/refine-ui/buttons/show";
import { DataTable } from "@/components/refine-ui/data-table/data-table";
import { ListView, ListViewHeader } from "@/components/refine-ui/views/list-view";
import { Badge } from "@/components/ui/badge";

type Sync = {
  id: string;
  name: string;
  query: string;
  schedule: string | null;
  status: string;
  last_run_at: string | null;
  created_at: string;
};

export default function ConnectionsList() {
  const columns = React.useMemo(() => {
    const columnHelper = createColumnHelper<Sync>();

    return [
      columnHelper.accessor("name", {
        id: "name",
        header: "Name",
        enableSorting: true,
      }),
      columnHelper.accessor("query", {
        id: "query",
        header: "Query",
        enableSorting: false,
        cell: ({ getValue }) => {
          const query = getValue();
          if (!query) return "-";
          return (
            <div className="max-w-xs truncate">{query.slice(0, 50)}...</div>
          );
        },
      }),
      columnHelper.accessor("schedule", {
        id: "schedule",
        header: "Schedule",
        enableSorting: false,
        cell: ({ getValue }) => getValue() || "Manual",
      }),
      columnHelper.accessor("status", {
        id: "status",
        header: "Status",
        enableSorting: true,
        cell: ({ getValue }) => {
          const status = getValue();
          const variant = status === "active" ? "default" : status === "paused" ? "secondary" : "outline";
          return (
            <Badge variant={variant}>
              {status}
            </Badge>
          );
        },
      }),
      columnHelper.accessor("last_run_at", {
        id: "last_run_at",
        header: "Last Run",
        enableSorting: true,
        cell: ({ getValue }) => {
          const date = getValue();
          return date ? new Date(date).toLocaleString() : "Never";
        },
      }),
      columnHelper.accessor("created_at", {
        id: "created_at",
        header: "Created At",
        enableSorting: true,
        cell: ({ getValue }) => {
          const date = getValue();
          return date ? new Date(date).toLocaleDateString() : "-";
        },
      }),
      columnHelper.display({
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <div className="flex gap-2">
            <EditButton recordItemId={row.original.id} size="sm" />
            <ShowButton recordItemId={row.original.id} size="sm" />
            <DeleteButton recordItemId={row.original.id} size="sm" />
          </div>
        ),
        enableSorting: false,
        size: 290,
      }),
    ];
  }, []);

  const table = useTable({
    columns,
    refineCoreProps: {
      syncWithLocation: true,
      resource: "syncs",
    },
  });

  return (
    <ListView>
      <ListViewHeader />
      <DataTable table={table} />
    </ListView>
  );
}
