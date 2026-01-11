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

type GoogleAdsConnection = {
  id: string;
  name: string;
  customer_id: string;
  conversion_action_id: string;
  status: string;
  last_tested_at: string | null;
  created_at: string;
};

export default function DestinationsList() {
  const columns = React.useMemo(() => {
    const columnHelper = createColumnHelper<GoogleAdsConnection>();

    return [
      columnHelper.accessor("name", {
        id: "name",
        header: "Name",
        enableSorting: true,
      }),
      columnHelper.accessor("customer_id", {
        id: "customer_id",
        header: "Customer ID",
        enableSorting: false,
      }),
      columnHelper.accessor("conversion_action_id", {
        id: "conversion_action_id",
        header: "Conversion Action",
        enableSorting: false,
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
      resource: "google_ads_connections",
    },
  });

  return (
    <ListView>
      <ListViewHeader />
      <DataTable table={table} />
    </ListView>
  );
}
