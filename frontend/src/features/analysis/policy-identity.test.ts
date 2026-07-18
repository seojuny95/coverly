import { describe, expect, test } from "vitest";

import { findByteIdenticalDuplicateIndexes } from "./policy-identity";
import type { AnalyzedInsurance } from "./store";

function documentWithFingerprint(fileFingerprint?: string): AnalyzedInsurance {
  return {
    id: fileFingerprint ?? "no-fingerprint",
    fileName: "policy.pdf",
    fileFingerprint,
    result: {
      status: "accepted",
      문자수: 10,
      기본정보: { 보험분류: "미분류", 상품태그: [] },
    },
  };
}

describe("findByteIdenticalDuplicateIndexes", () => {
  test("flags a fingerprint that matches an existing document", () => {
    const duplicates = findByteIdenticalDuplicateIndexes({
      fingerprints: ["aaa", "bbb"],
      existingDocuments: [documentWithFingerprint("bbb")],
    });

    expect(duplicates).toEqual(new Set([1]));
  });

  test("flags the later of two byte-identical files in the same batch", () => {
    const duplicates = findByteIdenticalDuplicateIndexes({
      fingerprints: ["ccc", "ccc"],
    });

    expect(duplicates).toEqual(new Set([1]));
  });

  test("returns no duplicates when fingerprints are all distinct and new", () => {
    const duplicates = findByteIdenticalDuplicateIndexes({
      fingerprints: ["aaa", "bbb"],
      existingDocuments: [documentWithFingerprint("zzz")],
    });

    expect(duplicates.size).toBe(0);
  });

  test("ignores existing documents without a fingerprint", () => {
    const duplicates = findByteIdenticalDuplicateIndexes({
      fingerprints: ["aaa"],
      existingDocuments: [documentWithFingerprint(undefined)],
    });

    expect(duplicates.size).toBe(0);
  });

  test("does not flag a missing candidate fingerprint", () => {
    const duplicates = findByteIdenticalDuplicateIndexes({
      fingerprints: [undefined, "aaa"],
      existingDocuments: [documentWithFingerprint("aaa")],
    });

    expect(duplicates).toEqual(new Set([1]));
  });
});
