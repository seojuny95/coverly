"use client";

import { useRef } from "react";

import { UploadRollbackError } from "../upload-helpers";

type DeleteSessionDocuments = (
  portfolioSessionToken: string,
  documentIds: string[],
) => Promise<void>;

type PendingCleanup = {
  portfolioSessionToken: string;
  documentIds: string[];
};

export function useUploadCleanup(
  deleteSessionDocuments: DeleteSessionDocuments,
) {
  const pendingCleanupRef = useRef<PendingCleanup | null>(null);

  const resolvePendingCleanup = async () => {
    const pendingCleanup = pendingCleanupRef.current;
    if (!pendingCleanup) return true;

    try {
      await deleteSessionDocuments(
        pendingCleanup.portfolioSessionToken,
        pendingCleanup.documentIds,
      );
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
      throw new UploadRollbackError();
    }
  };

  return {
    resolvePendingCleanup,
    rollbackSessionDocuments,
  };
}
