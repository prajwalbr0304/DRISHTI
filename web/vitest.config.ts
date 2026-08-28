import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// DRISHTI web — Vitest config (component + logic tests, jsdom environment).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: /^@testing-library\/react$/,
        replacement: fileURLToPath(new URL("./src/test/render.tsx", import.meta.url)),
      },
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
    ],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
});
