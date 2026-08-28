import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// DRISHTI web — Vite config.
// The API base is read at runtime from import.meta.env.VITE_API_BASE_URL;
// see src/api/client.ts. Mocks are the default so the shell runs standalone.
export default defineConfig(({ mode }) => {
  // Optional local-only bridge to a deployed API. The target uses a non-VITE
  // variable so it is never embedded in the browser bundle; requests remain
  // same-origin at /api and Vite forwards them server-side.
  const env = loadEnv(mode, process.cwd(), "");
  const devApiProxyTarget = env.DRISHTI_DEV_API_PROXY_TARGET?.trim();

  return {
    plugins: [react()],
    publicDir: "public",
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: 5173,
      strictPort: false,
      ...(devApiProxyTarget
        ? {
            proxy: {
              "/api": {
                target: devApiProxyTarget,
                changeOrigin: true,
                secure: true,
              },
            },
          }
        : {}),
    },
    preview: {
      port: 4173,
    },
  };
});
