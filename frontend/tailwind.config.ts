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
      },
      boxShadow: {
        panel: "0 10px 28px rgba(21, 29, 26, 0.07)",
      },
    },
  },
  plugins: [],
};

export default config;
