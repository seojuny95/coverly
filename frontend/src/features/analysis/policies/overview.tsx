"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { PolicyClassificationSummary } from "./classification-summary";
import { groupPolicyDocuments } from "./group-documents";
import { PolicyGroupList } from "./group-list";
import { PolicyOverviewHeader } from "./header";
import {
  loadUploadPolicyDocumentModal,
  preloadUploadPolicyDocumentModal,
} from "./load-upload-modal";
import { useExpandedPolicies } from "./use-expanded-policies";
import { PolicySummarySection } from "./summary-section";
import {
  useInsuranceData,
  type AnalyzedInsurance,
  type InsuranceAnalysis,
} from "../session/store";
import type { UploadPolicyDocument } from "@/features/upload/types";
import { PORTFOLIO_MAX_DOCUMENTS } from "@/shared/api/generated-runtime";

const EMPTY_DOCUMENTS: AnalyzedInsurance[] = [];

const LazyUploadPolicyDocumentModal = dynamic(
  () =>
    loadUploadPolicyDocumentModal().then(
      (module) => module.UploadPolicyDocumentModal,
    ),
  { loading: UploadPolicyDocumentModalLoading },
);

export function PolicyOverview({
  uploadPolicyDocument,
}: {
  uploadPolicyDocument?: UploadPolicyDocument;
} = {}) {
  const { analysis, sessionExpired, mergeDocuments, expireSession } =
    useInsuranceData();
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const { isExpanded, toggle } = useExpandedPolicies();

  const documents = analysis?.insuranceDocuments ?? EMPTY_DOCUMENTS;
  const groupedDocuments = useMemo(
    () => groupPolicyDocuments(documents),
    [documents],
  );
  const uploadLimitReached = documents.length >= PORTFOLIO_MAX_DOCUMENTS;
  const allowDocumentUpload = analysis?.portfolioKind === "uploaded";
  if (!analysis) return null;

  const openUploadModal = () => {
    if (allowDocumentUpload && !uploadLimitReached) setUploadModalOpen(true);
  };

  const preloadUploadModal = () => {
    if (allowDocumentUpload && !uploadLimitReached) {
      preloadUploadPolicyDocumentModal();
    }
  };

  const mergeAdditionalDocuments = (nextAnalysis: InsuranceAnalysis) => {
    mergeDocuments(nextAnalysis);
  };

  return (
    <>
      <PolicyOverviewHeader
        selectedName={analysis.selectedName}
        generatedAt={analysis.generatedAt}
        onOpenUploadModal={openUploadModal}
        onPreloadUploadModal={preloadUploadModal}
        uploadLimitReached={uploadLimitReached}
        allowDocumentUpload={allowDocumentUpload}
      />
      <PolicyClassificationSummary groupedDocuments={groupedDocuments} />
      <PolicySummarySection
        documents={documents}
        portfolioSessionToken={analysis.portfolioSessionToken}
        sessionExpired={sessionExpired}
        onSessionExpired={expireSession}
      />
      <PolicyGroupList
        groupedDocuments={groupedDocuments}
        isExpanded={isExpanded}
        onToggle={toggle}
      />

      {allowDocumentUpload && uploadModalOpen ? (
        <LazyUploadPolicyDocumentModal
          selectedName={analysis.selectedName}
          existingDocuments={documents}
          uploadPolicyDocument={uploadPolicyDocument}
          onClose={() => setUploadModalOpen(false)}
          onAnalysisComplete={mergeAdditionalDocuments}
        />
      ) : null}
    </>
  );
}

function UploadPolicyDocumentModalLoading() {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4 supports-backdrop-filter:backdrop-blur-sm">
      <div
        role="status"
        aria-live="polite"
        className="w-full max-w-sm rounded-2xl bg-white px-6 py-8 text-center text-sm text-zinc-600 shadow-2xl"
      >
        보험증권 추가 화면을 준비하고 있어요…
      </div>
    </div>
  );
}
