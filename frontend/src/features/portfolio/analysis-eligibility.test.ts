import { describe, expect, it } from "vitest";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import type { InsuranceUploadResult } from "../insurance-upload/upload-insurance";
import {
  emptyReasonFor,
  hasAnalyzableCoverage,
  isAnalyzableDocument,
  isAutoInsurance,
} from "./analysis-eligibility";

function makeResult(
  overrides: Partial<InsuranceUploadResult> = {},
): InsuranceUploadResult {
  return { status: "accepted", 문자수: 100, ...overrides };
}

function makeDoc(result: InsuranceUploadResult, id = "1"): AnalyzedInsurance {
  return { id, fileName: `${id}.pdf`, result };
}

describe("analysis-eligibility", () => {
  it("treats a real 담보 row as analyzable coverage", () => {
    const result = makeResult({
      보장목록: [
        { 담보명: "암진단", 가입금액: "3천만원", 보장내용: null, 해설: null },
      ],
    });
    expect(hasAnalyzableCoverage(result)).toBe(true);
  });

  it("does not count 부가-only rows as analyzable coverage", () => {
    const result = makeResult({
      보장목록: [
        {
          담보명: "요율",
          가입금액: "",
          보장내용: null,
          해설: null,
          유형: "부가",
        },
      ],
    });
    expect(hasAnalyzableCoverage(result)).toBe(false);
  });

  it("treats missing/empty 보장목록 as no analyzable coverage", () => {
    expect(hasAnalyzableCoverage(makeResult())).toBe(false);
    expect(hasAnalyzableCoverage(makeResult({ 보장목록: [] }))).toBe(false);
  });

  it("detects auto insurance by product tag", () => {
    expect(
      isAutoInsurance(
        makeResult({
          기본정보: { 보험분류: "손해보험", 상품태그: ["자동차보험"] },
        }),
      ),
    ).toBe(true);
    expect(
      isAutoInsurance(
        makeResult({
          기본정보: { 보험분류: "제3보험", 상품태그: ["실손보험"] },
        }),
      ),
    ).toBe(false);
  });

  it("is analyzable only when not damage insurance and has coverage", () => {
    const covered = makeResult({
      보장목록: [
        { 담보명: "암진단", 가입금액: "3천만원", 보장내용: null, 해설: null },
      ],
    });
    const damage = makeResult({
      기본정보: { 보험분류: "손해보험", 상품태그: ["자동차보험"] },
      보장목록: [
        { 담보명: "대인배상", 가입금액: "무한", 보장내용: null, 해설: null },
      ],
    });
    expect(isAnalyzableDocument(makeDoc(covered))).toBe(true);
    expect(isAnalyzableDocument(makeDoc(damage))).toBe(false);
    expect(isAnalyzableDocument(makeDoc(makeResult()))).toBe(false);
  });

  it("chooses an empty reason for non-eligible document sets", () => {
    const auto = makeDoc(
      makeResult({
        기본정보: { 보험분류: "손해보험", 상품태그: ["자동차보험"] },
      }),
      "a",
    );
    const noCov = makeDoc(makeResult(), "b");
    expect(emptyReasonFor([auto])).toBe("auto-only");
    expect(emptyReasonFor([noCov])).toBe("no-coverage");
    expect(emptyReasonFor([auto, noCov])).toBe("mixed");
  });
});
