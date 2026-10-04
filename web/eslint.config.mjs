import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "test-results/**",
      "e2e/**",
      "next-env.d.ts",
      "eslint.config.mjs",
    ],
  },
  // eslint-config-next still ships a legacy ("eslintrc") config; FlatCompat adapts it.
  ...compat.extends("next/core-web-vitals"),
  {
    rules: {
      // The table primitives take `cols`/`cells` as ReactNode[] and attach the
      // keys themselves when they map them (shared/warp-table.tsx). The rule
      // cannot follow JSX across that prop boundary, so every call site is a
      // false positive; adding keys at the call sites would be cargo-culting.
      "react/jsx-key": "off",
    },
  },
];

export default config;
