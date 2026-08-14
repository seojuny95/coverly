import { vi } from "vitest";

import { PolicyUploadForm } from "./upload-form";
import type { UploadPolicyDocument } from "../types";
import { isPdfPasswordProtected } from "./pdf-password-check";
import type {
  AnalyzedInsurance,
  InsuranceAnalysis,
} from "../../analysis/types";
import { useInsuranceData } from "../../analysis/session/store";
import { renderWithProviders } from "../../../test/render-with-providers";

function InsuranceDataProbe() {
  const { analysis, sessionExpired } = useInsuranceData();
  return (
    <>
      <div data-testid="probe">
        {(analysis?.insuranceDocuments ?? [])
          .map((document) => document.fileName)
          .join(",")}
      </div>
      <div data-testid="session-expired">{sessionExpired ? "yes" : "no"}</div>
    </>
  );
}

export const routerPush = vi.fn();
export const routerPrefetch = vi.fn();
const router = { push: routerPush, prefetch: routerPrefetch };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("./pdf-password-check", () => ({
  isPdfPasswordProtected: vi.fn(),
}));

export const passwordProtectedMock = vi.mocked(isPdfPasswordProtected);

export const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});
export const textFile = new File(["hello"], "note.txt", {
  type: "text/plain",
});
export const secondInsuranceFile = new File(
  ["%PDF-1.7\nsecond"],
  "second-insurance.pdf",
  {
    type: "application/pdf",
  },
);
export const createSession = vi.fn(async () => ({
  portfolioSessionToken: "test-portfolio-token",
  expiresAt: "2030-01-01T00:00:00.000Z",
  counselTurnsRemaining: 10,
}));
export const prepareServer = vi.fn(async () => undefined);

export function renderForm({
  uploadPolicyDocument = vi.fn(),
  onAnalysisComplete = vi.fn(),
  requiredInsuredPersonName,
  existingDocuments = [],
  prepareServer: prepareServerOverride = prepareServer,
  deleteSessionDocuments = vi.fn().mockResolvedValue(undefined),
  initialAnalysis = null,
}: {
  uploadPolicyDocument?: UploadPolicyDocument;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  requiredInsuredPersonName?: string;
  existingDocuments?: AnalyzedInsurance[];
  prepareServer?: (signal?: AbortSignal) => Promise<void>;
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
    signal?: AbortSignal,
  ) => Promise<void>;
  initialAnalysis?: InsuranceAnalysis | null;
} = {}) {
  const rendered = renderWithProviders(
    <>
      <PolicyUploadForm
        uploadPolicyDocument={uploadPolicyDocument}
        onAnalysisComplete={onAnalysisComplete}
        requiredInsuredPersonName={requiredInsuredPersonName}
        existingDocuments={existingDocuments}
        prepareServer={prepareServerOverride}
        createSession={createSession}
        deleteSessionDocuments={deleteSessionDocuments}
      />
      <InsuranceDataProbe />
    </>,
    { initialAnalysis },
  );
  return {
    uploadPolicyDocument,
    onAnalysisComplete,
    prepareServer: prepareServerOverride,
    deleteSessionDocuments,
    unmount: rendered.unmount,
  };
}

export function renderDefaultForm(uploadPolicyDocument: UploadPolicyDocument) {
  return renderWithProviders(
    <>
      <PolicyUploadForm
        uploadPolicyDocument={uploadPolicyDocument}
        prepareServer={prepareServer}
        createSession={createSession}
      />
      <InsuranceDataProbe />
    </>,
  );
}

export function resetFormTestState() {
  routerPush.mockClear();
  routerPrefetch.mockClear();
  createSession.mockClear();
  prepareServer.mockReset().mockResolvedValue(undefined);
  passwordProtectedMock.mockReset().mockResolvedValue(false);
}
