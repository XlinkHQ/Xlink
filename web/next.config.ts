import type { NextConfig } from "next";
import { readFileSync } from "fs";

const apiTarget = process.env.XLINK_API_URL || "http://api:8000";
const pkgVersion: string = (() => {
  try { return JSON.parse(readFileSync("./package.json", "utf-8")).version; } catch { return "0.0.0"; }
})();

// Optional secret admin path: when XLINK_WEB_PATH is set (e.g. "/a1b2c3d4") the
// panel is served under that prefix instead of "/", so a bare scan of the host
// finds nothing at the root. Empty = served at root (default). Set at build time
// — the installer builds the image with .env present. Must be a single leading
// slash and no trailing slash; we normalise defensively here too.
const rawBase = (process.env.XLINK_WEB_PATH || "").trim();
const basePath = rawBase && rawBase !== "/" ? `/${rawBase.replace(/^\/+|\/+$/g, "")}` : "";

const nextConfig: NextConfig = {
  output: "standalone",
  ...(basePath ? { basePath } : {}),
  env: {
    NEXT_PUBLIC_APP_VERSION: pkgVersion,
  },
  async rewrites() {
    // basePath does NOT prefix rewrite sources automatically for our API proxy,
    // so the app calls /api/* relative to basePath; Next strips basePath before
    // matching, so the source stays "/api/:path*".
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
