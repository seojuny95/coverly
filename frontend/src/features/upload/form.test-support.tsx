import { vi } from "vitest";

import { InsuranceUploadForm, type UploadInsurance } from "./form";
import { isPdfPasswordProtected } from "./pdf-password-check";
import type { AnalyzedInsurance, InsuranceAnalysis } from "../analysis/store";
import { useInsuranceData } from "../analysis/store";
import { renderWithProviders } from "../../test/render-with-providers";

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
  uploadInsurance = vi.fn(),
  onAnalysisComplete = vi.fn(),
  navigateToAnalysis = vi.fn(),
  existingDocuments = [],
  prepareServer: prepareServerOverride = prepareServer,
  deleteSessionDocuments = vi.fn().mockResolvedValue(undefined),
  initialAnalysis = null,
}: {
  uploadInsurance?: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis?: () => void;
  existingDocuments?: AnalyzedInsurance[];
  prepareServer?: (signal?: AbortSignal) => Promise<void>;
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
  ) => Promise<void>;
  initialAnalysis?: InsuranceAnalysis | null;
} = {}) {
  const rendered = renderWithProviders(
    <>
      <InsuranceUploadForm
        uploadInsurance={uploadInsurance}
        onAnalysisComplete={onAnalysisComplete}
        navigateToAnalysis={navigateToAnalysis}
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
    uploadInsurance,
    onAnalysisComplete,
    navigateToAnalysis,
    prepareServer: prepareServerOverride,
    deleteSessionDocuments,
    unmount: rendered.unmount,
  };
}

export function renderDefaultForm(uploadInsurance: UploadInsurance) {
  return renderWithProviders(
    <>
      <InsuranceUploadForm
        uploadInsurance={uploadInsurance}
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
