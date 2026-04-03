import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          icons: ["lucide-react"],
        },
      },
    },
  },
  server: {
    port: 3100,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/validate": {
        target: "http://localhost:8100",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8100",
        changeOrigin: true,
      },
      "/stats": {
        target: "http://localhost:8100",
        changeOrigin: true,
      },
      "/governance": {
        target: "http://localhost:8100",
        changeOrigin: true,
      },
    },
  },
});
