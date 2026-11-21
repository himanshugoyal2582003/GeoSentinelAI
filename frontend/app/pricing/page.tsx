import Link from "next/link";
import { ArrowRight, ArrowUpRight, Check, Crosshair, ShieldAlert } from "lucide-react";

export const metadata = {
  title: "Pricing and Free Site Audit | GeoSentinel AI",
  description: "Simple per-site pricing and a request form for a free 12-month satellite site audit.",
};

const includedFeatures = [
  "One monitored site, up to 25 hectares",
  "Custom boundary via GeoJSON, KML, or map drawing",
  "Scheduled Sentinel-2 checks around the five-day revisit",
  "Email alerts for clear, threshold-qualified changes (after delivery is configured)",
  "Downloadable branded scan reports",
];

export default function PricingPage() {
  return (
    <main className="pricing-shell">
      <header className="pricing-header">
        <Link className="landing-brand" href="/" aria-label="GeoSentinel home">
          <span className="brand-mark"><Crosshair size={19} /></span>
          <span className="landing-brand-copy"><strong>GeoSentinel AI</strong><small>Land-change monitoring</small></span>
        </Link>
        <nav className="pricing-nav" aria-label="Main navigation">
          <Link href="/dashboard">Live dashboard <ArrowUpRight size={14} /></Link>
          <Link className="pricing-nav-cta" href="#free-audit">Request a free audit <ArrowRight size={14} /></Link>
        </nav>
      </header>

      <section className="pricing-hero">
        <p className="pricing-eyebrow">CLEAR PRICING / INDIA</p>
        <h1>Know what your land is doing.<br /><em>Without a sales maze.</em></h1>
        <p className="pricing-intro">
          Request a no-cost historical review. Continue with scheduled satellite
          monitoring for one site at a straightforward price.
        </p>
      </section>

      <section className="pricing-plan" aria-labelledby="plan-title">
        <div className="pricing-plan-main">
          <p className="pricing-eyebrow">ONE SITE / ONE PLAN</p>
          <h2 id="plan-title">Site monitoring</h2>
          <p className="pricing-summary">For quarry boundaries, land banks, and larger plots.</p>
          <ul className="pricing-features">
            {includedFeatures.map((feature) => (
              <li key={feature}><Check size={16} aria-hidden="true" />{feature}</li>
            ))}
          </ul>
        </div>
        <div className="pricing-price">
          <span className="pricing-price-label">MONTH TO MONTH</span>
          <p><strong>₹1,499</strong><span> / site / month</span></p>
          <div className="pricing-annual">
            <span>Or ₹14,999 per site / year</span>
            <small>Save ₹2,989 compared with monthly billing.</small>
          </div>
          <Link className="pricing-primary" href="#free-audit">Request your free audit <ArrowRight size={16} /></Link>
          <small className="pricing-payment-note">No online payment is collected here. Onboarding and payment are arranged directly.</small>
        </div>
      </section>

      <section className="pricing-caveats" aria-label="Service details">
        <article>
          <span className="pricing-caveat-icon"><ShieldAlert size={18} /></span>
          <h3>Clouds can delay a clear result</h3>
          <p>Checks follow the Sentinel-2 revisit opportunity. Cloudy or unusable scenes are inconclusive, not proof that no change occurred.</p>
        </article>
        <article>
          <span className="pricing-caveat-icon"><Crosshair size={18} /></span>
          <h3>Screening, not a legal finding</h3>
          <p>Alerts require low cloud coverage, at least 1,000 m² of detected change, and at least 80% confidence. Verify permits and field conditions independently.</p>
        </article>
        <article>
          <span className="pricing-caveat-icon"><ArrowUpRight size={18} /></span>
          <h3>Email first, transparent always</h3>
          <p>Email alerts and downloadable scan reports are supported. WhatsApp delivery and automatic monthly reports are not included in this launch.</p>
        </article>
      </section>

      <section className="audit-request" id="free-audit" aria-labelledby="audit-title">
        <div className="audit-intro">
          <p className="pricing-eyebrow">START WITH EVIDENCE</p>
          <h2 id="audit-title">Request a free<br /><em>12-month site audit.</em></h2>
          <p>We’ll review the site details and follow up about available Sentinel-2 history. A useful comparison depends on clear imagery; this request does not automatically start a scan.</p>
          <p className="audit-privacy">Your request is collected by Netlify Forms after deployment. Share contact and general site details only; do not submit identity, ownership, or other sensitive documents.</p>
        </div>

        <form
          className="audit-form"
          name="free-audit"
          method="POST"
          action="/audit-requested"
          data-netlify="true"
          netlify-honeypot="bot-field"
        >
          <input type="hidden" name="form-name" value="free-audit" />
          <div hidden>
            <label>Leave this field empty: <input name="bot-field" /></label>
          </div>

          <label>
            Your name
            <input name="name" type="text" autoComplete="name" required maxLength={100} />
          </label>
          <label>
            Email address
            <input name="email" type="email" autoComplete="email" required maxLength={254} />
          </label>
          <label>
            Organization <span>(optional)</span>
            <input name="organization" type="text" autoComplete="organization" maxLength={120} />
          </label>
          <label>
            Site type
            <select name="site-type" required defaultValue="">
              <option value="" disabled>Select one</option>
              <option value="quarry">Quarry or lease boundary</option>
              <option value="farmhouse">Farmhouse or private plot</option>
              <option value="land-bank">Land bank or development parcel</option>
              <option value="consultancy">Environmental consultancy</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Site district and state
            <input name="site-location" type="text" autoComplete="address-level2" required maxLength={120} placeholder="For example, Pune, Maharashtra" />
          </label>
          <label>
            Approximate site area in hectares <span>(optional)</span>
            <input name="site-area-hectares" type="number" min="0.1" max="25" step="0.1" inputMode="decimal" />
          </label>
          <label className="audit-consent">
            <input name="contact-consent" type="checkbox" value="yes" required />
            <span>I agree to be contacted about this audit request.</span>
          </label>
          <button className="pricing-primary" type="submit">Send audit request <ArrowRight size={16} /></button>
          <small>By submitting, you’re asking us to contact you about this site review. No payment or account is created.</small>
        </form>
      </section>

      <footer className="pricing-footer">
        <Link href="/">GeoSentinel AI</Link>
        <span>Satellite change is an intelligence signal; verify before acting.</span>
        <Link href="/dashboard">Open dashboard <ArrowUpRight size={14} /></Link>
      </footer>
    </main>
  );
}
