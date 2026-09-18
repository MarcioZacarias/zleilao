/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        // Admin (skin neutro, igual ao Promo)
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
        },
        // Portal ("radar de leilões")
        radar: {
          bg: "#0b1020",
          surface: "#121a33",
          surface2: "#1a2447",
          text: "#e8ecf8",
          muted: "#93a0c4",
          border: "rgba(255,255,255,0.08)",
        },
        accent: {
          DEFAULT: "#f59e0b",
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
        },
      },
      boxShadow: {
        lift: "0 12px 30px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};
