"use client";

import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { PolicyUploadForm } from "../upload/form/upload-form";
import type { UploadPolicyDocument } from "../upload/types";
import type { AnalyzedInsurance, InsuranceAnalysis } from "./types";

export function UploadPolicyDocumentModal({
  selectedName,
  existingDocuments,
  uploadPolicyDocument,
  onClose,
  onAnalysisComplete,
}: {
  selectedName?: string;
  existingDocuments: AnalyzedInsurance[];
  uploadPolicyDocument?: UploadPolicyDocument;
  onClose: () => void;
  onAnalysisComplete: (analysis: InsuranceAnalysis) => void;
}) {
  const [isUploadInFlight, setIsUploadInFlight] = useState(false);

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !isUploadInFlight) onClose();
      }}
    >
      <DialogContent
        showCloseButton={false}
        onInteractOutside={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => {
          if (isUploadInFlight) e.preventDefault();
        }}
        className="w-full max-w-2xl rounded-2xl border border-zinc-200 bg-white p-5 shadow-[12px_12px_0_rgba(232,237,255,0.45)] sm:p-6"
      >
        <DialogHeader className="flex-row items-start justify-between gap-4 space-y-0">
          <DialogTitle className="text-xl font-semibold tracking-[-0.04em] text-zinc-950">
            보험증권 더 올리기
          </DialogTitle>
          <DialogClose asChild>
            <Button type="button" variant="ghost" disabled={isUploadInFlight}>
              닫기
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="mt-6">
          <PolicyUploadForm
            uploadPolicyDocument={uploadPolicyDocument}
            existingDocuments={existingDocuments}
            requiredInsuredPersonName={selectedName}
            onAnalysisComplete={(analysis) => {
              onAnalysisComplete(analysis);
              onClose();
            }}
            surface="modal"
            onUploadInFlightChange={setIsUploadInFlight}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
