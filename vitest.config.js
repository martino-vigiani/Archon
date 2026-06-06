import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@frontend": resolve(__dirname, "orchestrator/static/js"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/frontend/**/*.test.js"],
    setupFiles: ["tests/frontend/setup.js"],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "json"],
      reportsDirectory: ".orchestra/qa/coverage/frontend",
      include: ["orchestrator/static/js/**/*.js"],
      exclude: ["**/*.test.js"],
    },
  },
});
