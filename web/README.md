# XLink Web

RouterOS-inspired XLink console built with Next.js, TypeScript, Tailwind CSS,
TanStack Query-ready structure, and Recharts.

## Run

```bash
npm install
npm run dev
```

By default, local development proxies `/api/*` to `http://127.0.0.1:8000`.
Set `XLINK_API_URL` to override the backend origin, or `XLINK_PORT` when the
local API is running on another port.
