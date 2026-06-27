import type { NextConfig } from "next";
import { readFileSync } from "fs";

const apiTarget = process.env.XLINK_API_URL || "http://localhost:8010";
const pkgVersion: string = (() => {
  try { return JSON.parse(readFileSync("./package.json", "utf-8")).version; } catch { return "0.0.0"; }
})();

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_APP_VERSION: pkgVersion,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
      // serve the single-page console for clean screen paths (hard refresh / deep link)
      {
        source: "/:screen(nodes|profiles|groups|users|admins|settings|hosts|services)",
        destination: "/",
      },
    ];
  },
};

export default nextConfig;
