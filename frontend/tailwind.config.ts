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
        canvas: "#f4efe5",
        ink: "#16110c",
        ember: "#c9572f",
        pine: "#1f5440",
        mist: "#e7ddd0",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        panel: "0 18px 50px rgba(22, 17, 12, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;

