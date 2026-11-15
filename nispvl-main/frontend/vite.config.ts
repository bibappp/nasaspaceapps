import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: { "/api": { target: process.env.API_URL ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // крупные библиотеки — отдельными файлами: лучше кэшируются браузером
        manualChunks: { leaflet: ["leaflet", "react-leaflet", "@geoman-io/leaflet-geoman-free"], charts: ["recharts"], react: ["react", "react-dom", "react-router-dom", "i18next", "react-i18next"] },
      },
    },
  },
});
