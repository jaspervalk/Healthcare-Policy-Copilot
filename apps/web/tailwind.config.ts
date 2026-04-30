import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Single ink ramp for borders, text, and surface tints.
        ink: {
          50: "#f7f5f1",
          100: "#eeeae2",
          200: "#dfd9cd",
          300: "#c3bcae",
          400: "#8e8778",
          500: "#5e584d",
          600: "#3f3a32",
          700: "#2b2722",
          800: "#1d2733",
          900: "#13181f",
        },
        // Single primary action color.
        accent: {
          50: "#fbe9df",
          100: "#f4cab5",
          400: "#c06a43",
          500: "#a45736",
          600: "#894528",
        },
        // Sage as a secondary, used sparingly.
        sage: {
          400: "#8a956d",
          500: "#6f7a53",
          600: "#58623f",
        },
        // Surface tokens.
        surface: "#fbf9f5",
        canvas: "#f5efe5",
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "10px",
        md: "12px",
        lg: "16px",
        xl: "20px",
      },
      boxShadow: {
        soft: "0 1px 0 rgba(29, 39, 51, 0.04), 0 4px 14px rgba(29, 39, 51, 0.05)",
        lift: "0 1px 0 rgba(29, 39, 51, 0.06), 0 12px 30px rgba(29, 39, 51, 0.08)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "ui-serif", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
