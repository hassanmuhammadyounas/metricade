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

type BigQueryConnection = {
  id: string;
  name: string;
  project_id: string;
  dataset_id: string | null;
  status: string;
  last_tested_at: string | null;
  created_at: string;
};

export default function SourcesList() {
  const columns = React.useMemo(() => {
    const columnHelper = createColumnHelper<BigQueryConnection>();

    return [
      columnHelper.accessor("name", {
        id: "name",
        header: "Name",
        enableSorting: true,
      }),
      columnHelper.accessor("project_id", {
        id: "project_id",
        header: "Project ID",
        enableSorting: false,
      }),
      columnHelper.accessor("dataset_id", {
        id: "dataset_id",
        header: "Dataset ID",
        enableSorting: false,
        cell: ({ getValue }) => getValue() || "-",
      }),
      columnHelper.accessor("status", {
        id: "status",
        header: "Status",
        enableSorting: true,
        cell: ({ getValue }) => {
          const status = getValue();
          return (
            <Badge variant={status === "active" ? "default" : "secondary"}>
              {status}
            </Badge>
          );
        },
      }),
      columnHelper.accessor("last_tested_at", {
        id: "last_tested_at",
        header: "Last Tested",
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
      resource: "bigquery_connections",
    },
  });

  return (
    <ListView>
      <ListViewHeader />
      <DataTable table={table} />
    </ListView>
  );
}
