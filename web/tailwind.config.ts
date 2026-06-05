import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        router: {
          ink: "#16201f",
          panel: "#f3f5ef",
          border: "#cdd8cf",
          green: "#237864",
          darkGreen: "#0f4f43",
          lime: "#d8e6c8",
          warning: "#d7902f",
          danger: "#b84a3c",
        },
      },
      boxShadow: {
        router: "0 18px 50px rgba(22, 32, 31, 0.14)",
        insetPanel: "inset 0 1px 0 rgba(255,255,255,.82)",
      },
    },
  },
  plugins: [],
};

export default config;
