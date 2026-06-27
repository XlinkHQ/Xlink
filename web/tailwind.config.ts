import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--white)",
        canvas: "var(--bg-light)",
        subtle: "var(--bg-whitesmoke)",
        muted: "var(--bg-bright)",
        line: "var(--bg-medium)",
        hairline: "var(--hairline)",
        fg: {
          DEFAULT: "var(--body-color)",
          muted: "var(--body-muted)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          soft: "var(--primary-soft)",
          fg: "var(--on-primary)",
        },
        success: "var(--green)",
        warning: "var(--orange)",
        danger: {
          DEFAULT: "var(--red)",
          soft: "var(--red-error-bg)",
        },
      },
      borderRadius: {
        sm: "var(--corner-sm)",
        DEFAULT: "var(--corner)",
        md: "var(--corner-md)",
        lg: "var(--corner-lg)",
        xl: "var(--corner-xl)",
      },
      boxShadow: {
        card: "var(--shadow-sm)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        "elev-1": "var(--shadow-1)",
        pop: "0 4px 16px 0 rgba(0, 0, 0, 0.1)",
        "focus-ring": "0 0 0 2px var(--focus-ring)",
      },
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)"],
      },
    },
  },
  plugins: [],
};

export default config;
