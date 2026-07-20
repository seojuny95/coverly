import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { useState } from "react";
import { UploadInsuranceModal } from "./upload-modal";
import type { InsuranceAnalysis } from "./store";
import type { UploadInsurance } from "../upload/form";
import { isPdfPasswordProtected } from "../upload/pdf-password-check";
import { renderWithProviders } from "../../test/render-with-providers";
import { POLICY_PARSE_RESPONSE_DEFAULTS } from "../../test/api-fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("../upload/pdf-password-check", () => ({
  isPdfPasswordProtected: vi.fn(),
}));

vi.mock("./session-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./session-api")>()),
  createPortfolioSession: vi.fn(async () => ({
    portfolioSessionToken: "test-portfolio-token",
    expiresAt: "2030-01-01T00:00:00.000Z",
    counselTurnsRemaining: 10,
  })),
}));

const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});

function uploadOnePolicy() {
  return vi.fn<UploadInsurance>().mockResolvedValue({
    ...POLICY_PARSE_RESPONSE_DEFAULTS,
    status: "accepted",
    documentId: "test-document-id",
    문자수: 32,
    기본정보: {
      보험사: "삼성화재",
      상품명: "건강보험",
      계약자: "테스트고객",
      피보험자: "테스트고객",
      보험분류: "제3보험",
      상품태그: [],
    },
  });
}

beforeEach(() => {
  vi.mocked(isPdfPasswordProtected).mockReset().mockResolvedValue(false);
});

// Mirrors the analysis screen: closing the modal unmounts it, which is what
// would cancel an in-flight completion beat.
function ModalHost({
  uploadInsurance,
  onAnalysisComplete,
}: {
  uploadInsurance: UploadInsurance;
  onAnalysisComplete: (analysis: InsuranceAnalysis) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);
  if (!isOpen) return <p>모달이 닫혔어요</p>;
  return (
    <UploadInsuranceModal
      selectedName="테스트고객"
      existingDocuments={[]}
      uploadInsurance={uploadInsurance}
      onClose={() => setIsOpen(false)}
      onAnalysisComplete={onAnalysisComplete}
    />
  );
}

describe("UploadInsuranceModal", () => {
  test("keeps the finished upload when the user tries to close during the completion beat", async () => {
    const user = userEvent.setup();
    const onAnalysisComplete = vi.fn();
    renderWithProviders(
      <ModalHost
        uploadInsurance={uploadOnePolicy()}
        onAnalysisComplete={onAnalysisComplete}
      />,
    );

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "분석에 추가하기" }));

    expect(
      await screen.findByText("다 읽었어요. 결과를 보여드릴게요."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "닫기" }));
    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(onAnalysisComplete).toHaveBeenCalledWith(
        expect.objectContaining({
          insuranceDocuments: [
            expect.objectContaining({ fileName: "insurance.pdf" }),
          ],
        }),
      );
    });
    expect(await screen.findByText("모달이 닫혔어요")).toBeInTheDocument();
  });
});
