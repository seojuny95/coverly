import { describe, expect, it } from "vitest";

import nextConfig from "./next.config";

describe("security headers", () => {
  it("applies hardening headers to every route", async () => {
    const rules = await nextConfig.headers!();

    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/:path*");

    const byKey = Object.fromEntries(
      rules[0].headers.map((header) => [header.key, header.value]),
    );

    expect(byKey["X-Frame-Options"]).toBe("DENY");
    expect(byKey["X-Content-Type-Options"]).toBe("nosniff");
    expect(byKey["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(byKey["Permissions-Policy"]).toContain("camera=()");
    expect(byKey["Strict-Transport-Security"]).toContain("max-age=");
  });

  it("ships a CSP that blocks framing and plugins", async () => {
    const rules = await nextConfig.headers!();
    const csp = rules[0].headers.find(
      (header) => header.key === "Content-Security-Policy",
    )?.value;

    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    // The backend origin must be reachable via fetch.
    expect(csp).toContain("connect-src 'self'");
  });
});
