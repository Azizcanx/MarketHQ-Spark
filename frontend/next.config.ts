import type { NextConfig } from "next";

const backendOrigin =
  process.env.MARKETHQ_BACKEND_URL?.trim().replace(/\/+$/, "") ||
  "http://127.0.0.1:9999";

const exactBackendRoutes = [
  "/api/health",
  "/api/snapshot",
  "/api/schema",
  "/api/knowledge",
  "/api/brain",
  "/api/learning",
  "/api/strategy",
  "/api/pipeline",
  "/api/trade-chart",
  "/api/trades",
  "/api/trade",
  "/api/source-debug",
  "/api/symbols",
  "/api/evidence",
  "/api/hq/health",
];

const wildcardBackendRoutes = [
  "/api/workforce/:path*",
  "/api/hq/:path*",
  "/api/research/:path*",
  "/api/agents/:path*",
  "/api/auth/:path*",
];

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      ...exactBackendRoutes.map((source) => ({
        source,
        destination: `${backendOrigin}${source}`,
      })),
      ...wildcardBackendRoutes.map((source) => ({
        source,
        destination: `${backendOrigin}${source.replace(":path*",":path*")}`,
      })),
    ];
  },
};

export default nextConfig;
