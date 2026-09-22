import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { canonicalHostPlugin } from "./viteHost";

const clientOnly: Plugin = {
  name: "serenita-health-entry",
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      const path = (request.url ?? "").split("?")[0];
      if (["/admin", "/server", "/api/admin"].some(prefix => path === prefix || path.startsWith(prefix + "/"))) {
        response.statusCode = 404; response.setHeader("Content-Type", "text/plain; charset=utf-8");
        response.end("页面不存在"); return;
      }
      next();
    });
  },
  configurePreviewServer(server) {
    server.middlewares.use((request, response, next) => {
      const path = (request.url ?? "").split("?")[0];
      if (["/admin", "/server"].some(prefix => path === prefix || path.startsWith(prefix + "/"))) {
        response.statusCode = 404; response.end("页面不存在"); return;
      }
      next();
    });
  },
};

export default defineConfig({
  cacheDir: process.env.SERENITA_DEV_CANONICAL_HOST === "localhost"
    ? "node_modules/.vite/health-official" : "node_modules/.vite/health-self-hosted",
  plugins: [canonicalHostPlugin(process.env.SERENITA_DEV_CANONICAL_HOST ?? "127.0.0.1"), clientOnly, react()],
  build: { rollupOptions: { output: { manualChunks(id) {
    if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react-runtime";
  } } } },
  server: {
    host: "127.0.0.1", port: 5173,
    proxy: { "/api": { target: process.env.SERENITA_DEV_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
