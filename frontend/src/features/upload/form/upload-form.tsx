"use client";

import { useEffect } from "react";
import type {
  AnalyzedInsurance,
  InsuranceAnalysis,
} from "../../analysis/types";
import {
  createPortfolioSession,
  deletePortfolioSessionDocuments,
  type PortfolioSessionResult,
} from "../../analysis/session/api";
import { waitForBackendReady } from "@/shared/api/readiness";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { uploadPolicyDocument as uploadPolicyDocumentRequest } from "../api";
import { isPdfPasswordError } from "../errors";
import type { UploadPolicyDocument, UploadSurface } from "../types";
import { InsuredPersonSelection } from "./insured-person-selection";
import { PdfDropzone } from "./pdf-dropzone";
import { PolicyAnalysisProgress } from "./policy-analysis-progress";
import { PolicyDocumentGuide } from "./policy-document-guide";
import { SelectedFileList } from "./selected-file-list";
import { usePolicyUpload } from "./use-policy-upload";

type PolicyUploadFormProps = {
  uploadPolicyDocument?: UploadPolicyDocument;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  requiredInsuredPersonName?: string;
  existingDocuments?: AnalyzedInsurance[];
  surface?: UploadSurface;
  onInteractionLockedChange?: (isInteractionLocked: boolean) => void;
  disabled?: boolean;
  prepareServer?: (signal?: AbortSignal) => Promise<void>;
  createSession?: (signal?: AbortSignal) => Promise<PortfolioSessionResult>;
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
    signal?: AbortSignal,
  ) => Promise<void>;
};

const prepareUploadServer = (signal?: AbortSignal) =>
  waitForBackendReady({ signal });

export function PolicyUploadForm({
  uploadPolicyDocument,
  onAnalysisComplete,
  requiredInsuredPersonName,
  existingDocuments = [],
  surface = "page",
  onInteractionLockedChange,
  disabled = false,
  prepareServer = prepareUploadServer,
  createSession = createPortfolioSession,
  deleteSessionDocuments = deletePortfolioSessionDocuments,
}: PolicyUploadFormProps) {
  const upload = usePolicyUpload({
    uploadPolicyDocument: uploadPolicyDocument ?? uploadPolicyDocumentRequest,
    onAnalysisComplete,
    requiredInsuredPersonName,
    existingDocuments,
    prepareServer,
    createSession,
    deleteSessionDocuments,
  });

  const interactionLocked =
    upload.processingPhase !== null || Boolean(upload.pendingAnalysis);

  // A dismissible surface must stay mounted until every upload decision is complete.
  useEffect(() => {
    onInteractionLockedChange?.(interactionLocked);
  }, [interactionLocked, onInteractionLockedChange]);

  if (upload.processingPhase) {
    return (
      <PolicyAnalysisProgress
        progress={upload.analysisProgress}
        files={upload.selectedFiles.map((selectedFile) => ({
          name: selectedFile.file.name,
          status:
            selectedFile.status === "done"
              ? "done"
              : upload.processingPhase === "preparing-server"
                ? "waiting"
                : ("reading" as const),
        }))}
        surface={surface}
        phase={upload.processingPhase}
      />
    );
  }

  const passwordRetryFiles = upload.selectedFiles.filter((selectedFile) =>
    isPdfPasswordError(selectedFile.errorCode),
  );
  const submitDisabled =
    disabled ||
    upload.selectedFiles.length === 0 ||
    Boolean(upload.pendingAnalysis) ||
    (passwordRetryFiles.length > 0 &&
      passwordRetryFiles.some(
        (selectedFile) => !(selectedFile.password ?? "").trim(),
      )) ||
    upload.isCheckingPasswords;
  const isModal = surface === "modal";

  return (
    <form
      className={isModal ? "w-full max-w-none" : "w-full max-w-2xl"}
      onSubmit={upload.handleSubmit}
    >
      <PdfDropzone
        files={upload.selectedFiles}
        existingDocumentCount={existingDocuments.length}
        requiredInsuredPersonName={requiredInsuredPersonName}
        surface={surface}
        disabled={disabled || Boolean(upload.pendingAnalysis)}
        inputRef={upload.inputRef}
        onSelectFiles={upload.selectFiles}
      />

      {isModal ? null : (
        <>
          <UploadPrivacyNotice />
          <PolicyDocumentGuide />
        </>
      )}

      <div className="mt-4 flex flex-col gap-4">
        <SelectedFileList
          files={upload.selectedFiles}
          surface={surface}
          onRemove={upload.removeSelectedFile}
          onPasswordChange={upload.updateSelectedFilePassword}
          disableRemove={disabled || Boolean(upload.pendingAnalysis)}
        />
        <Button
          type="submit"
          disabled={submitDisabled}
          className={`self-stretch ${isModal ? "" : "sm:self-end"}`}
        >
          {isModal ? "분석에 추가하기" : "내 보험 분석하기"}
        </Button>
      </div>

      {upload.pendingAnalysis ? (
        <InsuredPersonSelection
          documents={upload.pendingAnalysis.insuranceDocuments}
          selectedName={upload.selectedName}
          onSelectedNameChange={upload.setSelectedName}
          onContinue={upload.handleNameSelectionSubmit}
        />
      ) : null}

      {upload.error ? (
        <Card
          role="alert"
          shadow="zinc"
          className="mt-4 rounded-xl px-4 py-3 text-sm leading-6 text-zinc-700"
        >
          {upload.error}
        </Card>
      ) : null}
    </form>
  );
}

function UploadPrivacyNotice() {
  return (
    <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-zinc-400">
      <span className="flex items-center gap-1.5">
        <PrivacyCheckIcon />
        개인정보는 가려서 처리해요
      </span>
      <span className="flex items-center gap-1.5">
        <PrivacyCheckIcon />
        가입 권유 전화가 가지 않아요
      </span>
    </div>
  );
}

function PrivacyCheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="size-3 text-blue-600"
      viewBox="0 0 14 14"
      fill="none"
    >
      <path
        d="m3 7 2.5 2.5L11 4.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="square"
      />
    </svg>
  );
}
