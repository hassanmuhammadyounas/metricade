import Link from "next/link";
import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata: Metadata = {
  title: "Terms of Service - Metricade",
  description: "Terms of Service for Metricade, a product owned and operated by Market Catalyst Enterprises LLC.",
};

export default function TermsPage() {
  const effectiveDate = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="flex min-h-screen flex-col items-center">
      <div className="w-full max-w-5xl px-4 py-12 md:py-16">
        <Button asChild variant="ghost" className="mb-8">
          <Link href="/">← Back to Home</Link>
        </Button>

        <div className="mb-8">
          <h1 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Terms of Service
          </h1>
          <p className="text-sm text-muted-foreground">Effective date: {effectiveDate}</p>
        </div>

        <Card>
          <CardContent className="prose prose-neutral max-w-none p-6 leading-relaxed dark:prose-invert md:p-10 [&>section]:mb-8 [&_h2]:mb-4 [&_h2]:mt-8 [&_p]:mb-4 [&_ul]:mb-4">
          <p>
            These Terms of Service (&quot;Terms&quot;) govern access to and use of Metricade and metricade.com (the &quot;Services&quot;). The Services are owned and operated by{" "}
            <a 
              href="https://marketcatalyst.org/" 
              target="_blank" 
              rel="noopener noreferrer"
              className="underline underline-offset-4"
            >
              Market Catalyst Enterprises LLC
            </a>{" "}
            (&quot;Company&quot;, &quot;we&quot;, &quot;us&quot;). By accessing or using the Services, you agree to these Terms.
          </p>

          <section>
            <h2 className="text-2xl font-semibold mb-4">1) Eligibility and account access</h2>
            <p className="text-muted-foreground">
              You must be legally able to enter into a binding contract to use the Services. Access to the Services may be limited to approved users (e.g., private beta). You are responsible for all activity conducted through your account or credentials.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">2) Use of the Services</h2>
            <p className="text-muted-foreground mb-3">You agree to use the Services only in compliance with applicable laws and these Terms. You will not:</p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Use the Services to violate any law, regulation, or third-party rights;</li>
              <li>Attempt to gain unauthorized access to the Services or related systems;</li>
              <li>Interfere with or disrupt the integrity or performance of the Services;</li>
              <li>Use the Services to create or distribute malware or abusive content.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">3) Third-party services</h2>
            <p className="text-muted-foreground">
              The Services may integrate with third-party platforms (e.g., data warehouses or advertising platforms). Your use of third-party services is governed by their terms and policies. We are not responsible for third-party services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">4) Customer configurations and instructions</h2>
            <p className="text-muted-foreground">
              You control the configurations you set within the Services, including what systems you connect and what data you instruct the Services to process or transmit. You represent that you have all rights and permissions necessary to provide such instructions and to process any data transmitted through the Services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">5) No advertising management</h2>
            <p className="text-muted-foreground">
              Metricade is a data synchronization and reporting tool. It does not provide advertising management services and does not create or modify ads, campaigns, bids, budgets, or targeting.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">6) Intellectual property</h2>
            <p className="text-muted-foreground">
              We retain all rights, title, and interest in and to the Services, including all related software, trademarks, and intellectual property. These Terms do not grant you any ownership rights in the Services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">7) Confidentiality</h2>
            <p className="text-muted-foreground">
              If you receive non-public information from us about the Services, you agree to keep it confidential and use it only as necessary to evaluate or use the Services.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">8) Disclaimers</h2>
            <p className="text-muted-foreground">
              THE SERVICES ARE PROVIDED &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot;. TO THE MAXIMUM EXTENT PERMITTED BY LAW, WE DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">9) Limitation of liability</h2>
            <p className="text-muted-foreground">
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, THE COMPANY WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS, REVENUE, DATA, OR GOODWILL, ARISING OUT OF OR RELATED TO YOUR USE OF THE SERVICES.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">10) Indemnification</h2>
            <p className="text-muted-foreground">
              You agree to indemnify and hold harmless the Company from and against any claims, liabilities, damages, losses, and expenses arising out of or related to your use of the Services, your data, or your violation of these Terms.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">11) Termination</h2>
            <p className="text-muted-foreground">
              We may suspend or terminate access to the Services at any time for any reason, including if we reasonably believe you have violated these Terms or the use poses a security or legal risk.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">12) Changes</h2>
            <p className="text-muted-foreground">
              We may update these Terms from time to time. The &quot;Effective date&quot; above indicates when the Terms were last updated. Continued use after updates constitutes acceptance.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">13) Governing law</h2>
            <p className="text-muted-foreground">
              These Terms are governed by the laws of the State of New Mexico, USA, without regard to conflict of laws principles.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">14) Contact</h2>
            <p className="text-muted-foreground">
              For questions about these Terms, contact: <a href="mailto:support@metricade.com" className="underline underline-offset-4 hover:text-foreground">support@metricade.com</a>
            </p>
          </section>
          </CardContent>
        </Card>

        <Separator className="my-8" />

        <div className="flex justify-between">
          <Button asChild variant="outline">
            <Link href="/">← Back to Home</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/privacy">Privacy Policy →</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
