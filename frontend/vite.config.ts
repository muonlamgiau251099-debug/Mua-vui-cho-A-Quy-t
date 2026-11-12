/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: Vite (5173) chuyển tiếp /api và /ws sang backend FastAPI (8000).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"], // e2e/ do Playwright chạy riêng
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
