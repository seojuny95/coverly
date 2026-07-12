import { describe, expect, it } from "vitest";

import { safeHref } from "./safe-href";

describe("safeHref", () => {
  it("passes through safe schemes", () => {
    expect(safeHref("https://example.com/claim")).toBe(
      "https://example.com/claim",
    );
    expect(safeHref("http://example.com")).toBe("http://example.com");
    expect(safeHref("tel:1588-1234")).toBe("tel:1588-1234");
    expect(safeHref("mailto:help@example.com")).toBe("mailto:help@example.com");
  });

  it("allows ordinary same-origin relative paths", () => {
    expect(safeHref("/portfolio")).toBe("/portfolio");
    expect(safeHref("/claims/guide")).toBe("/claims/guide");
  });

  it("drops protocol-relative and backslash-authority URLs", () => {
    expect(safeHref("//evil.com")).toBeUndefined();
    expect(safeHref("/\\evil.com")).toBeUndefined();
    expect(safeHref("\\\\evil.com")).toBeUndefined();
  });

  it("drops dangerous schemes", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("  javascript:alert(1)  ")).toBeUndefined();
    expect(
      safeHref("data:text/html,<script>alert(1)</script>"),
    ).toBeUndefined();
    expect(safeHref("vbscript:msgbox(1)")).toBeUndefined();
    // Tab/newline/CR are stripped before the scheme check, so this can't
    // smuggle a javascript: scheme past the allowlist.
    expect(safeHref("java\tscript:alert(1)")).toBeUndefined();
  });

  it("returns undefined for empty/nullish input", () => {
    expect(safeHref(undefined)).toBeUndefined();
    expect(safeHref("")).toBeUndefined();
    expect(safeHref("   ")).toBeUndefined();
  });
});
