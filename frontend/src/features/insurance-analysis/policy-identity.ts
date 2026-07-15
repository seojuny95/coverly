import type { AnalyzedInsurance } from "./insurance-analysis-store";

function normalizeValue(value: string) {
  return value.trim().replace(/\s+/g, "").toLowerCase();
}

export function normalizeInsurerName(value: string) {
  return normalizeValue(value).replace(/주식회사|\(주\)|㈜/g, "");
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

// Byte-level duplicate check that runs BEFORE upload, using only the SHA-256
// fingerprints already computed for each selected file. Catches re-adding the
// exact same file (against existing documents or earlier in the same batch)
// without paying for a full parse + LLM pass. Content-identical-but-rebyted
// copies fall through to findDuplicatePolicyDocuments after parsing.
export function findByteIdenticalDuplicateIndexes({
  fingerprints,
  existingDocuments = [],
}: {
  fingerprints: Array<string | undefined>;
  existingDocuments?: AnalyzedInsurance[];
}): Set<number> {
  const seenFingerprints = new Set<string>();
  for (const document of existingDocuments) {
    if (document.fileFingerprint) {
      seenFingerprints.add(document.fileFingerprint);
    }
  }

  const duplicateIndexes = new Set<number>();
  fingerprints.forEach((fingerprint, index) => {
    if (!fingerprint) return;

    if (seenFingerprints.has(fingerprint)) {
      duplicateIndexes.add(index);
      return;
    }

    seenFingerprints.add(fingerprint);
  });

  return duplicateIndexes;
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
