import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, API calls to /api are proxied to the backend so the SPA and API share
// an origin (cookies + CSRF work without CORS complications).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8080,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
