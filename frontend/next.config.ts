import type { NextConfig } from "next";

// The browser talks to the backend directly (NEXT_PUBLIC_API_BASE_URL), so the
// backend origin must be allowlisted in connect-src or fetches are CSP-blocked.
const backendOrigin = (() => {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8000";
  }
})();

const isDev = process.env.NODE_ENV !== "production";

// Pragmatic CSP: there is no nonce pipeline yet, so Next's inline bootstrap
// script and inline styles need 'unsafe-inline'. This is defense-in-depth — the
// app has no dangerouslySetInnerHTML and react-markdown sanitizes URLs. A
// nonce-based script-src is a possible follow-up. 'unsafe-eval' is dev-only (HMR).
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  // ws:/wss: (dev only) so the Next HMR websocket isn't refused by connect-src.
  `connect-src 'self' ${backendOrigin}${isDev ? " ws: wss:" : ""}`,
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), browsing-topics=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
];

const nextConfig: NextConfig = {
  reactCompiler: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
