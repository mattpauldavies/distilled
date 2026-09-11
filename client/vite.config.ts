/// <reference types="vitest/config" />
import { sentryVitePlugin } from "@sentry/vite-plugin"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    sentryVitePlugin({
      org: "distilled-metrics",
      project: "distilled-client",
      sourcemaps: {
        // Maps go to Sentry for symbolication, never to the web root — a
        // served .map reconstructs the full original TypeScript for anyone.
        filesToDeleteAfterUpload: "./dist/**/*.map",
      },
    }),
  ],

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    env: {
      VITE_CLERK_PUBLISHABLE_KEY: "pk_test_placeholder",
      VITE_API_BASE_URL: "",
    },
  },

  build: {
    // "hidden" emits maps for the Sentry plugin without a sourceMappingURL
    // pointer, so browsers never discover them even if a map slips through.
    sourcemap: "hidden",
  },
})
