import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta MareNostrum (azul "mar")
        brand: {
          50: "#eef6ff",
          100: "#d9eaff",
          500: "#1e6fd9",
          600: "#1657ae",
          700: "#114589",
          900: "#0a2752",
        },
      },
    },
  },
  plugins: [],
};
export default config;
