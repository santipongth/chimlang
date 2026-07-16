import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// dev: proxy ทุก endpoint ของ FastAPI (:8000) — prod: FastAPI เสิร์ฟ dist ที่ /app
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/app/",
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["echarts/core", "echarts/charts", "echarts/components", "echarts/renderers", "cytoscape"],
          query: ["@tanstack/react-query", "openapi-fetch"],
          vendor: ["react", "react-dom", "lucide-react"],
        },
      },
    },
  },
  server: {
    proxy: Object.fromEntries(
      ["/dashboard.json", "/signal.json", "/citizen", "/graph", "/health"].map((p) => [
        p,
        { target: "http://localhost:8000", changeOrigin: true },
      ]),
    ),
  },
});
