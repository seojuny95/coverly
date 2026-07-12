import type { AnalyzedInsurance } from "./insurance-analysis-store";

function normalizeValue(value: string) {
  return value.trim().replace(/\s+/g, "").toLowerCase();
}

export function normalizeInsurerName(value: string) {
  return normalizeValue(value).replace(/주식회사|\(주\)|㈜/g, "");
}

export function getPolicyIdentityKey(
  insuranceDocument: AnalyzedInsurance,
): string | null {
  return getPolicyIdentityKeys(insuranceDocument)[0] ?? null;
}

export function getPolicyIdentityKeys(
  insuranceDocument: AnalyzedInsurance,
): string[] {
  const keys: string[] = [];

  const basicInfo = insuranceDocument.result.기본정보;
  if (basicInfo) {
    const insurer = basicInfo.보험사
      ? normalizeInsurerName(basicInfo.보험사)
      : "";
    const policyNumber = basicInfo.증권번호
      ? normalizeValue(basicInfo.증권번호)
      : "";

    if (insurer && policyNumber) {
      keys.push(`policy-number:${insurer}:${policyNumber}`);
    }

    const productName = basicInfo.상품명
      ? normalizeValue(basicInfo.상품명)
      : "";
    const insuredName = basicInfo.피보험자
      ? normalizeValue(basicInfo.피보험자)
      : "";
    const startDate = basicInfo.보험기간?.시작일
      ? normalizeValue(basicInfo.보험기간.시작일)
      : "";
    const endDate = basicInfo.보험기간?.종료일
      ? normalizeValue(basicInfo.보험기간.종료일)
      : "";

    if (insurer && productName && insuredName && startDate && endDate) {
      keys.push(
        `policy-period:${insurer}:${productName}:${insuredName}:${startDate}:${endDate}`,
      );
    }
  }

  if (insuranceDocument.fileFingerprint) {
    keys.push(`file:${insuranceDocument.fileFingerprint}`);
  }

  return keys;
}

export function findDuplicatePolicyDocuments({
  candidates,
  existingDocuments = [],
}: {
  candidates: AnalyzedInsurance[];
  existingDocuments?: AnalyzedInsurance[];
}) {
  const seenKeys = new Set<string>();
  const duplicates: AnalyzedInsurance[] = [];

  for (const document of existingDocuments) {
    for (const key of getPolicyIdentityKeys(document)) {
      seenKeys.add(key);
    }
  }

  for (const document of candidates) {
    const keys = getPolicyIdentityKeys(document);
    if (keys.length === 0) continue;

    if (keys.some((key) => seenKeys.has(key))) {
      duplicates.push(document);
      continue;
    }

    for (const key of keys) {
      seenKeys.add(key);
    }
  }

  return duplicates;
}
