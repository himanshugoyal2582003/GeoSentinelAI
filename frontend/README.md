# Frontend

The frontend is a Next.js 16 and React application with static export
configured for deployment to Netlify.

## Local development

From this directory run `npm install` and `npm run dev`. Set
`NEXT_PUBLIC_API_URL` in the build environment to override the default local
API URL. Use `npm run build` to validate the production export.

- [`app/`](./app/) contains routes and shared UI.
- [`package.json`](./package.json) defines the scripts and dependencies.
- [`next.config.ts`](./next.config.ts) configures the Next.js build.

See [`docs/operations.md`](../docs/operations.md) for deployment settings.
