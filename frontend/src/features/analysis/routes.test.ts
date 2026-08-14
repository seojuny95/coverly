import { describe, expect, it } from "vitest";

import { isAnalysisPath } from "./routes";

describe("isAnalysisPath", () => {
  it.each(["/analysis", "/analysis/coverage", "/analysis/chat"])(
    "recognizes %s as part of the analysis route",
    (pathname) => {
      expect(isAnalysisPath(pathname)).toBe(true);
    },
  );

  it.each(["/", "/upload", "/analysis-old"])(
    "rejects %s outside the analysis route",
    (pathname) => {
      expect(isAnalysisPath(pathname)).toBe(false);
    },
  );
});
