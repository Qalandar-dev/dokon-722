import type { NextConfig } from "next";

/**
 * In Docker, Nginx routes `/api` and `/media` to FastAPI, so the browser only ever
 * talks to one origin. For `npm run dev` without Nginx, set API_PROXY_TARGET
 * (e.g. http://localhost:8000) and Next.js forwards those paths instead.
 */
const apiProxyTarget = process.env.API_PROXY_TARGET;
const isDev = process.env.NODE_ENV !== "production";

// Everything comes from our own origin. Next.js needs inline scripts for hydration
// ('unsafe-inline'); the dev server additionally needs eval for hot reloading.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self'${isDev ? " ws:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Product images are served by Nginx as uploaded; the image optimizer is not used,
  // so it is switched off to keep its attack surface out of production.
  images: { unoptimized: true },
  async rewrites() {
    if (!apiProxyTarget) return [];
    return [
      { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
      { source: "/media/:path*", destination: `${apiProxyTarget}/media/:path*` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
