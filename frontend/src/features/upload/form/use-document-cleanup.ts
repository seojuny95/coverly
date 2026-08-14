import { useRef } from "react";

import { UploadedDocumentCleanupError } from "../errors";

type DeleteSessionDocuments = (
  portfolioSessionToken: string,
  documentIds: string[],
  signal?: AbortSignal,
) => Promise<void>;

type PendingCleanup = {
  portfolioSessionToken: string;
  documentIds: string[];
};

export function useServerDocumentCleanup(
  deleteSessionDocuments: DeleteSessionDocuments,
) {
  const pendingCleanupRef = useRef<PendingCleanup | null>(null);

  const resolvePendingCleanup = async (signal?: AbortSignal) => {
    const pendingCleanup = pendingCleanupRef.current;
    if (!pendingCleanup) return true;

    try {
      if (signal) {
        await deleteSessionDocuments(
          pendingCleanup.portfolioSessionToken,
          pendingCleanup.documentIds,
          signal,
        );
      } else {
        await deleteSessionDocuments(
          pendingCleanup.portfolioSessionToken,
          pendingCleanup.documentIds,
        );
      }
      pendingCleanupRef.current = null;
      return true;
    } catch {
      return false;
    }
  };

  const rollbackSessionDocuments = async (
    portfolioSessionToken: string | undefined,
    documentIds: string[],
  ) => {
    if (!portfolioSessionToken || documentIds.length === 0) return [];

    const uniqueDocumentIds = [...new Set(documentIds)];
    try {
      await deleteSessionDocuments(portfolioSessionToken, uniqueDocumentIds);
      pendingCleanupRef.current = null;
      return uniqueDocumentIds;
    } catch {
      pendingCleanupRef.current = {
        portfolioSessionToken,
        documentIds: uniqueDocumentIds,
      };
      throw new UploadedDocumentCleanupError();
    }
  };

  return {
    resolvePendingCleanup,
    rollbackSessionDocuments,
  };
}
