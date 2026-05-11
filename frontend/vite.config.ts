import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev: Vite serves React on :5173 and proxies /api → FastAPI on :8000,
// so the frontend and backend look like one origin (no CORS in the app).
// In prod: FastAPI serves the built bundle from frontend/dist as static
// files at /, so there's no separate Vite server and no proxy hop.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
