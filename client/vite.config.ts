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
      VITE_GITHUB_APP_SLUG: "test-app",
    },
  },

  build: {
    sourcemap: true,
  },
})
