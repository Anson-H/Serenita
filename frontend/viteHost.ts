import type { Plugin } from "vite";

export function canonicalHostPlugin(hostname: string | undefined): Plugin {
  return { name: "serenita-canonical-host",
    configureServer(server) {
      if (!hostname) return;
      server.middlewares.use((request, response, next) => {
        if ((request.headers.host ?? "").split(":")[0] === hostname) return next();
        response.statusCode = 403;
        response.setHeader("Content-Type", "text/plain; charset=utf-8");
        response.end(`This development server is only available at ${hostname}.`);
      });
    },
    configurePreviewServer(server) {
      if (!hostname) return;
      server.middlewares.use((request, response, next) => {
        if ((request.headers.host ?? "").split(":")[0] === hostname) return next();
        response.statusCode = 403; response.end("Invalid application host.");
      });
    } };
}
