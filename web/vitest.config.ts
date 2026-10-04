import { configDefaults, defineConfig } from "vitest/config";
import { resolve } from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@": resolve(__dirname),
    },
  },
  test: {
    // e2e/ is the Playwright browser check (`npm run test:e2e`), not a unit test.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
