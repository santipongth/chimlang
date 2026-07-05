import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// dev: proxy ทุก endpoint ของ FastAPI (:8000) — prod: FastAPI เสิร์ฟ dist ที่ /app
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/app/",
  server: {
    proxy: Object.fromEntries(
      ["/dashboard.json", "/signal.json", "/citizen", "/graph", "/health"].map((p) => [
        p,
        { target: "http://localhost:8000", changeOrigin: true },
      ]),
    ),
  },
});
