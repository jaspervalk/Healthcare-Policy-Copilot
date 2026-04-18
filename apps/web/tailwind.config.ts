import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sand: "#f5efe5",
        slate: "#1d2733",
        moss: "#6f7a53",
        clay: "#c06a43",
        paper: "#fffdf8",
      },
      boxShadow: {
        card: "0 18px 60px rgba(27, 38, 49, 0.08)",
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(29,39,51,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(29,39,51,0.08) 1px, transparent 1px)",
      },
    },
  },
  plugins: [],
};

export default config;

