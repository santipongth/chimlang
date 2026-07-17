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
        onlyExplicitManualChunks: true,
        manualChunks(id) {
          if (/node_modules\/(react|react-dom|lucide-react)\//.test(id)) return "vendor";
          if (/node_modules\/(react-router|react-router-dom|@remix-run\/router)\//.test(id)) return "router";
          if (/node_modules\/(@tanstack\/react-query|openapi-fetch)\//.test(id)) return "query";
          if (id.includes("/node_modules/cytoscape/")) return "graph";
          if (id.includes("/node_modules/echarts/")) return "charts";
        },
      },
    },
  },
  server: {
    proxy: Object.fromEntries(
      [
        "/dashboard.json", "/signal.json", "/graph", "/health",
        "/runs", "/run-jobs", "/run-metrics.json", "/simruns.json", "/settings",
        "/experiments", "/engines.json", "/personas", "/gallery", "/watchlists",
        "/alerts", "/calibration.json", "/predictions", "/observability.json", "/compare.json",
      ].map((path) => [
        path,
        { target: "http://localhost:8000", changeOrigin: true },
      ]),
    ),
  },
});
