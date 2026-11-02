/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Geliştirmede tarayıcı yalnızca bu sunucuyla konuşur; /api istekleri
// Codespace'in içinden FastAPI'ye (8000) aktarılır. Böylece API portunu
// dışarı açmak ve CORS ayarı gerekmez. Canlıda aynı işi Caddy yapar.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: [".app.github.dev", "localhost", "127.0.0.1"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
