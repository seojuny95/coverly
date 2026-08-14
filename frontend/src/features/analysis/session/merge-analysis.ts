import { getPolicyIdentityKeys } from "../policy-identity";
import type { AnalyzedInsurance, InsuranceAnalysis } from "../types";

// Merge by document id first, then by policy identity as a defensive boundary.
export function mergeInsuranceAnalysis(
  current: InsuranceAnalysis,
  next: InsuranceAnalysis,
): InsuranceAnalysis {
  const documentsById = new Map<string, AnalyzedInsurance>();
  const identityKeyCounts = new Map<string, number>();
  const identityKeysByDocumentId = new Map<string, string[]>();

  const removeIdentityKeys = (documentId: string) => {
    for (const key of identityKeysByDocumentId.get(documentId) ?? []) {
      const nextCount = (identityKeyCounts.get(key) ?? 0) - 1;
      if (nextCount > 0) identityKeyCounts.set(key, nextCount);
      else identityKeyCounts.delete(key);
    }
    identityKeysByDocumentId.delete(documentId);
  };

  const storeDocument = (document: AnalyzedInsurance, keys: string[]) => {
    removeIdentityKeys(document.id);
    documentsById.set(document.id, document);
    identityKeysByDocumentId.set(document.id, keys);
    for (const key of keys) {
      identityKeyCounts.set(key, (identityKeyCounts.get(key) ?? 0) + 1);
    }
  };

  for (const document of current.insuranceDocuments) {
    storeDocument(document, getPolicyIdentityKeys(document));
  }

  for (const document of next.insuranceDocuments) {
    const identityKeys = getPolicyIdentityKeys(document);
    const replacesExistingDocument = documentsById.has(document.id);

    if (replacesExistingDocument) removeIdentityKeys(document.id);

    const duplicatesExistingPolicy = identityKeys.some((key) =>
      identityKeyCounts.has(key),
    );

    if (duplicatesExistingPolicy && !replacesExistingDocument) {
      continue;
    }

    storeDocument(document, identityKeys);
  }

  return {
    generatedAt: next.generatedAt,
    selectedName: next.selectedName ?? current.selectedName,
    portfolioSessionToken: next.portfolioSessionToken,
    portfolioSessionExpiresAt: next.portfolioSessionExpiresAt,
    // Merging in another upload must never hand back spent question turns.
    counselTurnsRemaining: Math.min(
      current.counselTurnsRemaining,
      next.counselTurnsRemaining,
    ),
    insuranceDocuments: [...documentsById.values()],
  };
}
