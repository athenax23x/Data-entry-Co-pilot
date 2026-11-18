import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The build goes straight into the Python package; FastAPI serves it at "/" (see merchant_notebook/api/app.py).
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../merchant_notebook/api/static", emptyOutDir: true, sourcemap: false },
  test: { environment: "jsdom", globals: true, include: ["src/**/*.test.{ts,tsx}"] },
});
