import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#f6f7f3",
        ink: "#151d1a",
        ember: "#ad4b34",
        pine: "#146052",
        mist: "#dfe7e1",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        panel: "0 1px 2px rgba(21, 29, 26, 0.04), 0 8px 24px rgba(21, 29, 26, 0.05)",
        lift: "0 2px 4px rgba(21, 29, 26, 0.06), 0 12px 32px rgba(21, 29, 26, 0.09)",
      },
    },
  },
  plugins: [],
};

export default config;
