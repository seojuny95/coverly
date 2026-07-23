import type {
  AnalyzedInsurance,
  InsuranceAnalysis,
} from "../../analysis/store";
import type { SelectedUploadFile } from "../types";
import type { SuccessfulUploadTransaction } from "./upload-transaction";
import { validateUploadedAnalysis } from "./name-validation";

export type ValidationWorkflowOutcome = "finished" | "retained";

export async function resolveUploadValidation({
  transaction,
  selectedUploadFiles,
  existingDocuments,
  fixedSelectedName,
  failSelectedFiles,
  rejectDuplicateFiles,
  setError,
  onComplete,
  onSelectName,
}: {
  transaction: SuccessfulUploadTransaction;
  selectedUploadFiles: SelectedUploadFile[];
  existingDocuments: AnalyzedInsurance[];
  fixedSelectedName?: string;
  failSelectedFiles: (
    files: Array<{ id: string; fileName: string }>,
    code: "MISSING_INSURED_PERSON",
    message: string,
  ) => void;
  rejectDuplicateFiles: (
    files: Array<{ id: string; fileName: string }>,
  ) => void;
  setError: (error: string) => void;
  onComplete: (analysis: InsuranceAnalysis, selectedName: string) => void;
  onSelectName: (analysis: InsuranceAnalysis, selectedName: string) => void;
}): Promise<ValidationWorkflowOutcome> {
  const validation = validateUploadedAnalysis({
    analysis: transaction.analysis,
    selectedUploadFiles,
    fileFingerprints: transaction.fileFingerprints,
    existingDocuments,
    fixedSelectedName,
  });
  const selectedFilesForDocuments = (documents: AnalyzedInsurance[]) =>
    documents.flatMap((document) => {
      const selectedFileId = transaction.selectedFileIdsByDocumentId.get(
        document.id,
      );
      return selectedFileId
        ? [{ id: selectedFileId, fileName: document.fileName }]
        : [];
    });

  switch (validation.kind) {
    case "byte-identical-duplicate":
      await transaction.rollbackUploadedDocuments();
      rejectDuplicateFiles(
        validation.selectedFiles.map((selectedFile) => ({
          id: selectedFile.id,
          fileName: selectedFile.file.name,
        })),
      );
      return "finished";
    case "missing-insured-person":
      await transaction.rollbackUploadedDocuments();
      failSelectedFiles(
        selectedFilesForDocuments(validation.documents),
        "MISSING_INSURED_PERSON",
        "피보험자를 확인할 수 없는 증권이에요.",
      );
      return "finished";
    case "duplicate-policy":
      await transaction.rollbackUploadedDocuments();
      rejectDuplicateFiles(selectedFilesForDocuments(validation.documents));
      return "finished";
    case "fixed-name-mismatch":
      await transaction.rollbackUploadedDocuments();
      setError(
        `${fixedSelectedName}님의 보험증권만 추가할 수 있어요. 같은 피보험자의 증권만 선택해주세요.`,
      );
      return "finished";
    case "complete":
      onComplete(transaction.analysis, validation.selectedName);
      return "retained";
    case "select-name":
      onSelectName(transaction.analysis, validation.selectedName);
      return "retained";
  }
}
