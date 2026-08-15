"use client";

import { useMemo, useState } from "react";

import { PolicyClassificationSummary } from "./classification-summary";
import { groupPolicyDocuments } from "./group-documents";
import { PolicyGroupList } from "./group-list";
import { PolicyOverviewHeader } from "./header";
import { UploadPolicyDocumentModal } from "./upload-modal";
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

  const mergeAdditionalDocuments = (nextAnalysis: InsuranceAnalysis) => {
    mergeDocuments(nextAnalysis);
  };

  return (
    <>
      <PolicyOverviewHeader
        selectedName={analysis.selectedName}
        generatedAt={analysis.generatedAt}
        onOpenUploadModal={openUploadModal}
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
        <UploadPolicyDocumentModal
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
