import Link from "next/link";
import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata: Metadata = {
  title: "Privacy Policy - Metricade",
  description: "Privacy Policy for Metricade, a product owned and operated by Market Catalyst Enterprises LLC.",
};

export default function PrivacyPage() {
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
            Privacy Policy
          </h1>
          <p className="text-sm text-muted-foreground">Effective date: {effectiveDate}</p>
        </div>

        <Card>
          <CardContent className="prose prose-neutral max-w-none p-6 leading-relaxed dark:prose-invert md:p-10 [&>section]:mb-8 [&_h2]:mb-4 [&_h2]:mt-8 [&_h3]:mb-3 [&_h3]:mt-6 [&_p]:mb-4 [&_ul]:mb-4">
          <p>
            Metricade (&quot;Metricade&quot;, &quot;we&quot;, &quot;us&quot;) is a product owned and operated by{" "}
            <a 
              href="https://marketcatalyst.org/" 
              target="_blank" 
              rel="noopener noreferrer"
              className="underline underline-offset-4"
            >
              Market Catalyst Enterprises LLC
            </a>{" "}
            (&quot;Company&quot;). This Privacy Policy explains how we collect, use, and disclose information when you visit metricade.com or use Metricade (the &quot;Services&quot;).
          </p>

          <section>
            <h2 className="text-2xl font-semibold mb-4">1) Information we collect</h2>
            
            <h3 className="text-xl font-semibold mb-3 mt-6">a) Information you provide</h3>
            <p className="text-muted-foreground">
              If you contact us, request access, or otherwise communicate with us, we may collect your name, email address, company name, and the contents of your message.
            </p>

            <h3 className="text-xl font-semibold mb-3 mt-6">b) Usage and device information</h3>
            <p className="text-muted-foreground">
              We may automatically collect limited technical information when you visit our website, such as IP address, device type, browser type, pages visited, and approximate location derived from IP address. We use this information to secure and operate the website and to understand aggregate usage.
            </p>

            <h3 className="text-xl font-semibold mb-3 mt-6">c) Customer data processed by the Services</h3>
            <p className="text-muted-foreground">
              If you use Metricade, you may connect external systems (such as a data warehouse or advertising account) and instruct the Services to process conversion or measurement data. The specific data processed depends on your configuration and what you choose to connect and upload. We process such data solely to provide the Services and as instructed by the user or customer.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">2) How we use information</h2>
            <p className="text-muted-foreground mb-3">We use information to:</p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>Provide, operate, maintain, and improve the Services;</li>
              <li>Respond to inquiries and provide support;</li>
              <li>Secure the Services and prevent abuse or fraud;</li>
              <li>Comply with legal obligations.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">3) How we share information</h2>
            <p className="text-muted-foreground mb-3">We do not sell personal information. We may share information:</p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>With service providers that help us operate the Services (e.g., hosting, logging, email), under contractual confidentiality obligations;</li>
              <li>With external platforms you connect (e.g., advertising platforms) when you direct the Services to send data to them;</li>
              <li>For legal reasons if required to comply with law, regulation, or valid legal process, or to protect the rights, property, or safety of the Company, users, or others.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">4) Data retention</h2>
            <p className="text-muted-foreground">
              We retain information for as long as necessary to provide the Services and for legitimate business purposes, including security, compliance, and dispute resolution. Retention periods may vary depending on data type and configuration.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">5) Security</h2>
            <p className="text-muted-foreground">
              We implement reasonable administrative, technical, and organizational measures designed to protect information. No method of transmission or storage is completely secure, and we cannot guarantee absolute security.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">6) International processing</h2>
            <p className="text-muted-foreground">
              The Services may be accessed from different countries. Information may be processed in jurisdictions where we or our service providers operate.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">7) Your choices</h2>
            <p className="text-muted-foreground">
              You may contact us to request access to, correction of, or deletion of personal information we hold about you, subject to legal and operational limitations.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">8) Third-party links and services</h2>
            <p className="text-muted-foreground">
              The Services may link to third-party websites or services. We are not responsible for their privacy practices. Your use of third-party services is governed by their terms and privacy policies.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">9) Changes to this policy</h2>
            <p className="text-muted-foreground">
              We may update this Privacy Policy from time to time. The &quot;Effective date&quot; above indicates when it was last updated.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold mb-4">10) Contact</h2>
            <p className="text-muted-foreground">
              For privacy inquiries, contact: <a href="mailto:support@metricade.com" className="underline underline-offset-4 hover:text-foreground">support@metricade.com</a>
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
            <Link href="/terms">Terms of Service →</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
