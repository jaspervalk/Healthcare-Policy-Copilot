import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Cool slate ramp. Replaces the warm-tinted ramp; no yellow.
        ink: {
          50: "#f4f6f8",
          100: "#e6eaef",
          200: "#d0d6dd",
          300: "#b1bac4",
          400: "#7c8693",
          500: "#54616f",
          600: "#364556",
          700: "#1f2c3b",
          800: "#0f1d2b",
          900: "#061321",
        },
        // Primary action color — deep teal-blue. Healthcare-tech signature,
        // distinct from the warm-cream AI palette family.
        primary: {
          50: "#e7f2f4",
          100: "#c5dfe4",
          200: "#9bc7cf",
          400: "#1f7e8f",
          500: "#146675",
          600: "#0e505d",
        },
        // Status / danger accent. Cooler coral than the previous burnt orange,
        // used only for danger states and the rare warm cue.
        accent: {
          50: "#fef0e8",
          100: "#fbd7c2",
          400: "#d27855",
          500: "#ad5a3c",
          600: "#8a4528",
        },
        surface: "#f7f9fb",
        canvas: "#eef2f5",
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "10px",
        md: "12px",
        lg: "16px",
        xl: "20px",
      },
      boxShadow: {
        soft: "0 1px 0 rgba(15, 29, 43, 0.04), 0 4px 14px rgba(15, 29, 43, 0.05)",
        lift: "0 1px 0 rgba(15, 29, 43, 0.06), 0 12px 30px rgba(15, 29, 43, 0.08)",
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
