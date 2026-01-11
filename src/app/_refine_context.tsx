"use client";

import { Refine } from "@refinedev/core";
import { RefineKbar, RefineKbarProvider } from "@refinedev/kbar";
import React from "react";

import routerProvider from "@refinedev/nextjs-router";

import "@/app/globals.css";
import { Toaster } from "@/components/refine-ui/notification/toaster";
import { useNotificationProvider } from "@/components/refine-ui/notification/use-notification-provider";
import { ThemeProvider } from "@/components/refine-ui/theme/theme-provider";
import { authProviderClient } from "@providers/auth-provider/auth-provider.client";
import { dataProvider } from "@providers/data-provider";
import { TRPCProvider } from "@/utils/trpc";

type RefineContextProps = {
  children: React.ReactNode;
};

export const RefineContext = ({ children }: RefineContextProps) => {
  const notificationProvider = useNotificationProvider();

  return (
    <TRPCProvider>
      <RefineKbarProvider>
        <ThemeProvider>
          <Refine
            authProvider={authProviderClient}
            dataProvider={dataProvider}
            notificationProvider={notificationProvider}
            routerProvider={routerProvider}
            resources={[
              {
                name: "bigquery_connections",
                list: "/sources",
                create: "/sources/create",
                edit: "/sources/edit/:id",
                show: "/sources/show/:id",
                meta: {
                  label: "Sources",
                  canDelete: true,
                },
              },
              {
                name: "google_ads_connections",
                list: "/destinations",
                create: "/destinations/create",
                edit: "/destinations/edit/:id",
                show: "/destinations/show/:id",
                meta: {
                  label: "Destinations",
                  canDelete: true,
                },
              },
              {
                name: "syncs",
                list: "/connections",
                create: "/connections/create",
                edit: "/connections/edit/:id",
                show: "/connections/show/:id",
                meta: {
                  label: "Connections",
                  canDelete: true,
                },
              },
              {
                name: "sync_runs",
                list: "/syncs",
                show: "/syncs/show/:id",
                meta: {
                  label: "Syncs",
                  canDelete: false,
                },
              },
            ]}
            options={{
              syncWithLocation: true,
              warnWhenUnsavedChanges: true,
              disableTelemetry: false,
              title: {
                text: "Metricade",
              },
            }}
          >
            {children}
            <Toaster />
            <RefineKbar />
          </Refine>
        </ThemeProvider>
      </RefineKbarProvider>
    </TRPCProvider>
  );
};
