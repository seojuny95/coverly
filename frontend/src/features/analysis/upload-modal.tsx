import { ghostButtonClassName } from "../../shared/components/coverly-brand";
import { InsuranceUploadForm, type UploadInsurance } from "../upload/form";
import type { AnalyzedInsurance, InsuranceAnalysis } from "./store";
import { useDialogA11y } from "./use-dialog-a11y";

export function UploadInsuranceModal({
  selectedName,
  existingDocuments,
  uploadInsurance,
  onClose,
  onAnalysisComplete,
}: {
  selectedName?: string;
  existingDocuments: AnalyzedInsurance[];
  uploadInsurance?: UploadInsurance;
  onClose: () => void;
  onAnalysisComplete: (analysis: InsuranceAnalysis) => void;
}) {
  const dialogRef = useDialogA11y<HTMLDivElement>({ open: true, onClose });

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/45 px-5 py-8 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-upload-modal-title"
      tabIndex={-1}
    >
      <div className="w-full max-w-2xl rounded-2xl border border-zinc-200 bg-white p-5 shadow-[12px_12px_0_rgba(232,237,255,0.45)] sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="analysis-upload-modal-title"
              className="text-xl font-semibold tracking-[-0.04em] text-zinc-950"
            >
              보험증권 더 올리기
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={ghostButtonClassName}
          >
            닫기
          </button>
        </div>

        <div className="mt-6">
          <InsuranceUploadForm
            uploadInsurance={uploadInsurance}
            existingDocuments={existingDocuments}
            fixedSelectedName={selectedName}
            onAnalysisComplete={onAnalysisComplete}
            navigateToAnalysis={onClose}
            surface="modal"
          />
        </div>
      </div>
    </div>
  );
}
