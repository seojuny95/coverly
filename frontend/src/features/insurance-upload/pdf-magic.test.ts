import { describe, expect, it } from "vitest";

import { fileHasPdfMagic, hasPdfMagicBytes } from "./pdf-magic";

const encode = (text: string) => new TextEncoder().encode(text);

describe("hasPdfMagicBytes", () => {
  it("accepts a PDF signature at the start", () => {
    expect(hasPdfMagicBytes(encode("%PDF-1.7\n...binary..."))).toBe(true);
  });

  it("accepts a PDF signature after a leading BOM/whitespace", () => {
    expect(hasPdfMagicBytes(encode("﻿  %PDF-1.4"))).toBe(true);
  });

  it("rejects non-PDF content", () => {
    expect(hasPdfMagicBytes(encode("PKzip-content"))).toBe(false);
    expect(hasPdfMagicBytes(encode("<html></html>"))).toBe(false);
    expect(hasPdfMagicBytes(new Uint8Array())).toBe(false);
  });
});

describe("fileHasPdfMagic", () => {
  it("is true for a real PDF file", async () => {
    const file = new File([encode("%PDF-1.7 body")], "policy.pdf", {
      type: "application/pdf",
    });
    expect(await fileHasPdfMagic(file)).toBe(true);
  });

  it("is false for a non-PDF renamed to .pdf", async () => {
    const file = new File([encode("PNG\r\n")], "not-really.pdf", {
      type: "application/pdf",
    });
    expect(await fileHasPdfMagic(file)).toBe(false);
  });
});
