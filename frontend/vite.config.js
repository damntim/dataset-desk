import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development (npm run dev) the website runs on :5173 and forwards /api/... to the
// API on :8000, removing the /api prefix. In Docker, nginx does the same job (nginx.conf).
// Same address for page and API = no CORS setup needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_URL || "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
