import Link from "next/link";
import { ArrowLeft, Check } from "lucide-react";

export const metadata = {
  title: "Audit Request Received | GeoSentinel AI",
  description: "Your GeoSentinel free site-audit request was received.",
};

export default function AuditRequestedPage() {
  return (
    <main className="pricing-shell audit-confirmation">
      <div className="audit-confirmation-mark"><Check size={25} aria-hidden="true" /></div>
      <p className="pricing-eyebrow">REQUEST RECEIVED</p>
      <h1>Thanks for reaching out.</h1>
      <p>Your audit request has been submitted. We’ll review the site details and contact you about available imagery and next steps.</p>
      <p className="audit-confirmation-note">A request is not a completed audit or a guarantee of cloud-free historical imagery.</p>
      <Link className="pricing-primary" href="/pricing"><ArrowLeft size={16} /> Back to pricing</Link>
    </main>
  );
}
