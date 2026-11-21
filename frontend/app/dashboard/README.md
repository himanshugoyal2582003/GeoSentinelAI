# Monitoring dashboard

[`page.tsx`](./page.tsx) implements the live dashboard: static-region
refreshes, custom monitoring sites, findings, map interactions, training
controls, and PDF reports. Automatic satellite refreshes use a 30-minute
cadence and the backend's shared cache; cached results are labeled in the UI.

The API base URL comes from `NEXT_PUBLIC_API_URL`. Keep API contract changes
aligned with [`docs/api-reference.md`](../../../docs/api-reference.md).
