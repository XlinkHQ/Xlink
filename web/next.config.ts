import type { NextConfig } from "next";
import { readFileSync } from "fs";

const apiTarget =
  process.env.XLINK_API_URL || `http://127.0.0.1:${process.env.XLINK_PORT || "8000"}`;
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
    ];
  },
};

export default nextConfig;
