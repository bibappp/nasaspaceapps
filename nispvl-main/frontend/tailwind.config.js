/** @type {import('tailwindcss').Config} */
// Дизайн-система Агро-Севооборота: светлые поверхности, тёмно-зелёный акцент, графитовый текст.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      colors: {
        // основной акцент — тёмно-зелёный; палитра field сохранена для совместимости с прежними компонентами
        field: { 50: "#F1F6F2", 100: "#E2EDE5", 200: "#C4DACB", 300: "#9DC0A8", 500: "#2E6B47", 600: "#26603F", 700: "#1F5134", 800: "#183F29", 900: "#10301E" },
        ink: { DEFAULT: "#1F2328", 2: "#3D444D", muted: "#5B6470", subtle: "#8A929C" },
        line: { DEFAULT: "#E3E6EA", strong: "#CDD2D8" },
        surface: { DEFAULT: "#F6F7F6", raised: "#FFFFFF", sunken: "#EEF1EF" },
        soil: { 50: "#F8F5F0", 100: "#EFE7DA", 300: "#CDB48F", 500: "#8C6A3F", 700: "#5F4728", 900: "#33260F" },
        wheat: { 100: "#FBF3DF", 300: "#EBCB7C", 500: "#C9971F" },
        status: { good: "#1F7A4D", warn: "#B45309", bad: "#B42318", info: "#1D4ED8" },
      },
      fontSize: { base: ["0.9375rem", "1.5rem"] },
      borderRadius: { DEFAULT: "6px", md: "6px", lg: "8px", xl: "10px", "2xl": "10px" },
      boxShadow: {
        sm: "0 1px 2px rgba(16, 24, 40, 0.05)",
        DEFAULT: "0 1px 3px rgba(16, 24, 40, 0.08), 0 1px 2px rgba(16, 24, 40, 0.04)",
        lg: "0 8px 24px rgba(16, 24, 40, 0.10)",
      },
    },
  },
  plugins: [],
};
