import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Declared to TypeScript in tsconfig.app.json and to the bundler here. Both need it:
    // tsc resolves the types, Rollup resolves the module.
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // The API is proxied in development so the browser sees one origin. That keeps the
    // refresh cookie a first-party cookie, which is what makes an httpOnly session work
    // without loosening SameSite.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
