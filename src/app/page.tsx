import Link from "next/link";
import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export const metadata: Metadata = {
  title: "Metricade - Reverse ETL for Advertising Attribution",
  description: "Metricade enables organizations to synchronize permitted conversion and measurement data from their data warehouse to advertising platforms for attribution and reporting.",
};

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      {/* Hero Section */}
      <section className="flex w-full flex-col items-center justify-center px-4 py-24 md:py-32 lg:py-40">
        <div className="flex w-full max-w-7xl flex-col items-center gap-8">
          <Badge variant="outline" className="text-sm">
            In Development / Private Beta
          </Badge>
          
          <div className="flex w-full max-w-[980px] flex-col items-center gap-6 text-center">
            <h1 className="text-4xl font-bold leading-tight tracking-tighter md:text-6xl lg:text-7xl lg:leading-[1.1]">
              Metricade
            </h1>
            <p className="max-w-[750px] text-lg text-muted-foreground sm:text-xl">
              Metricade is a reverse ETL product that enables organizations to synchronize permitted conversion and measurement data from their data warehouse to advertising platforms for attribution and reporting.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4">
            <Button asChild size="lg">
              <a href="mailto:support@metricade.com">Contact Us</a>
            </Button>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="flex w-full justify-center px-4 py-16 md:py-24">
        <div className="grid w-full max-w-6xl gap-8 md:grid-cols-2">
          {/* What it does */}
          <Card className="border-2">
            <CardContent className="p-6 md:p-8">
              <h3 className="mb-6 text-xl font-semibold">What Metricade does</h3>
              <ul className="space-y-4 text-muted-foreground">
                <li className="flex items-start gap-3">
                  <span className="mt-1 text-foreground">✓</span>
                  <span>Connects to customer-managed data warehouses (e.g., BigQuery).</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="mt-1 text-foreground">✓</span>
                  <span>Transforms and maps customer-provided conversion events for upload where permitted.</span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="mt-1 text-foreground">✓</span>
                  <span>Supports reporting and configuration through limited, read-only metadata access.</span>
                </li>
              </ul>
            </CardContent>
          </Card>

          {/* What it doesn't do */}
          <Card className="border-2">
            <CardContent className="p-6 md:p-8">
              <h3 className="mb-6 text-xl font-semibold">What Metricade does not do</h3>
              <p className="text-muted-foreground">
                Metricade is not an advertising management service and does not create or modify ads, campaigns, bids, budgets, or targeting.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Company Info */}
      <section className="flex w-full justify-center px-4 py-16">
        <div className="w-full max-w-3xl text-center">
          <p className="text-sm text-muted-foreground">
            Metricade is a product owned and operated by{" "}
            <a 
              href="https://marketcatalyst.org/" 
              target="_blank" 
              rel="noopener noreferrer"
              className="underline underline-offset-4 transition-colors hover:text-foreground"
            >
              Market Catalyst Enterprises LLC
            </a>.
          </p>
        </div>
      </section>

      <div className="flex w-full justify-center px-4">
        <Separator className="w-full max-w-7xl" />
      </div>

      {/* Footer */}
      <footer className="flex w-full justify-center px-4 py-8">
        <div className="flex w-full max-w-7xl flex-col items-center justify-between gap-4 md:flex-row">
          <div className="flex gap-4 text-sm text-muted-foreground">
            <Link href="/privacy" className="transition-colors hover:text-foreground">
              Privacy Policy
            </Link>
            <Link href="/terms" className="transition-colors hover:text-foreground">
              Terms
            </Link>
          </div>
          <p className="text-sm text-muted-foreground">
            Contact: <a href="mailto:support@metricade.com" className="transition-colors hover:text-foreground">
              support@metricade.com
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
