# Pricing and Free Audit

## Published offer

| Term | Price | Scope |
|---|---:|---|
| Monthly | ₹1,499 per site / month | One monitoring polygon, with a plan limit of 25 hectares |
| Annual | ₹14,999 per site / year | Same scope; ₹2,989 less than twelve monthly payments |

Onboarding and payment are arranged manually. The site does not collect payment
details or create a subscription.

The plan page describes the current service honestly:

- scheduled Sentinel-2 checks are based on the approximately five-day revisit;
  cloudy or unavailable scenes can delay a useful comparison;
- automated email alerts currently require cloud coverage below 20%, a finding
  of at least 1,000 m², and confidence of at least 80%;
- branded scan reports can be downloaded for persisted scans;
- WhatsApp delivery and automatic monthly report generation are not currently
  implemented.

These are screening signals, not legal determinations. Review satellite
imagery, permits, and field conditions before taking action.

## Free 12-month audit request

The `/pricing` page contains a Netlify Forms submission for a no-cost request.
It collects a name, email, optional organization and area, site category,
district/state, and consent to be contacted. It does not accept boundary files
or identity/ownership documents.

The form only creates a request; it does not trigger a scan or generate an
audit automatically. Historical scene availability and cloud coverage must be
reviewed before confirming the audit scope. The requester is told this on the
page and confirmation route.

After deploying the static site to Netlify:

1. Confirm the form named `free-audit` is listed in the Netlify Forms panel.
2. Submit a test request and verify it appears there.
3. Confirm the configured notification and retention policy before collecting
   real contact information.
4. Add the exact Netlify site origin (and any custom domain) to Render's
   `CORS_ORIGINS`; no path or wildcard is required.

Local Next.js development does not store form submissions.

## Launch QA still requiring live inputs

Before describing the offer as operational, test one user-authorized real
polygon each for a quarry, farmhouse plot, and land bank. For each, verify the
boundary, scene dates and cloud status, persisted scan, and branded PDF.
Sentinel-2's 10 m pixels cannot establish small boundary-wall or parcel-level
events; the free audit is not a substitute for title, permit, or field review.

The current site does not include payment processing or automated historical
audit generation. Do not claim either capability until it is implemented and
verified.
