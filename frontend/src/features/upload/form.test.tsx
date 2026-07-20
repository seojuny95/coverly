import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi, beforeEach } from "vitest";

import { InsuranceUploadForm, type UploadInsurance } from "./form";
import { UploadInsuranceError } from "./api";
import { isPdfPasswordProtected } from "./pdf-password-check";
import type { AnalyzedInsurance, InsuranceAnalysis } from "../analysis/store";
import { useInsuranceData } from "../analysis/store";
import { renderWithProviders } from "../../test/render-with-providers";
import {
  POLICY_PARSE_RESPONSE_DEFAULTS,
  POLICY_RESULT_DEFAULTS,
} from "../../test/api-fixtures";

// Probe consumer: reads the in-memory context so tests can assert what the
// form wrote via the default onAnalysisComplete (setAnalysis).
function InsuranceDataProbe() {
  const { analysis } = useInsuranceData();
  return (
    <div data-testid="probe">
      {(analysis?.insuranceDocuments ?? [])
        .map((document) => document.fileName)
        .join(",")}
    </div>
  );
}

const routerPush = vi.fn();
const routerPrefetch = vi.fn();
const router = { push: routerPush, prefetch: routerPrefetch };
vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

// Real PDF parsing (pdfjs-dist) is an external browser boundary, so unit
// tests stub it and default to "not encrypted" unless a test overrides it.
vi.mock("./pdf-password-check", () => ({
  isPdfPasswordProtected: vi.fn(),
}));

const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});
const textFile = new File(["hello"], "note.txt", {
  type: "text/plain",
});
const secondInsuranceFile = new File(
  ["%PDF-1.7\nsecond"],
  "second-insurance.pdf",
  {
    type: "application/pdf",
  },
);
const createSession = vi.fn(async () => ({
  portfolioSessionToken: "test-portfolio-token",
  expiresAt: "2030-01-01T00:00:00.000Z",
  counselTurnsRemaining: 10,
}));

function renderForm({
  uploadInsurance = vi.fn(),
  onAnalysisComplete = vi.fn(),
  navigateToAnalysis = vi.fn(),
  existingDocuments = [],
  deleteSessionDocuments = vi.fn().mockResolvedValue(undefined),
}: {
  uploadInsurance?: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis?: () => void;
  existingDocuments?: AnalyzedInsurance[];
  deleteSessionDocuments?: (
    portfolioSessionToken: string,
    documentIds: string[],
  ) => Promise<void>;
} = {}) {
  renderWithProviders(
    <InsuranceUploadForm
      uploadInsurance={uploadInsurance}
      onAnalysisComplete={onAnalysisComplete}
      navigateToAnalysis={navigateToAnalysis}
      existingDocuments={existingDocuments}
      createSession={createSession}
      deleteSessionDocuments={deleteSessionDocuments}
    />,
  );
  return {
    uploadInsurance,
    onAnalysisComplete,
    navigateToAnalysis,
    deleteSessionDocuments,
  };
}

beforeEach(() => {
  routerPush.mockClear();
  routerPrefetch.mockClear();
  createSession.mockClear();
  vi.mocked(isPdfPasswordProtected).mockReset().mockResolvedValue(false);
});

describe("InsuranceUploadForm", () => {
  test("prefetches the programmatic analysis destination", async () => {
    renderForm();

    await waitFor(() => {
      expect(routerPrefetch).toHaveBeenCalledWith("/analysis");
    });
  });

  test("disables upload until a file is selected", () => {
    renderForm();

    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });

  test("shows where to get a policy document on demand", async () => {
    const user = userEvent.setup();
    renderForm();

    const guide = screen.getByTestId("policy-document-guide");
    expect(guide).not.toHaveAttribute("open");

    await user.click(screen.getByText("보험증권을 어디서 받는지 모르겠어요"));

    expect(guide).toHaveAttribute("open");
    expect(
      screen.getByText("보험증권을 이렇게 받을 수 있어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/보험사 앱·홈페이지 → 계약 관리 또는 증명서 발급/),
    ).toBeInTheDocument();

    const insurerLookupLink = screen.getByRole("link", {
      name: "가입한 보험사 확인 (새 창에서 열기)",
    });
    expect(insurerLookupLink).toHaveAttribute(
      "href",
      "https://cont.insure.or.kr/cont_web/intro.do",
    );
    expect(insurerLookupLink).toHaveAttribute("target", "_blank");
  });

  test("selects a PDF through the file picker", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);

    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("shows the backend error for a non-PDF renamed to .pdf", async () => {
    const user = userEvent.setup();
    const fakePdf = new File(["this is not a pdf at all"], "fake.pdf", {
      type: "application/pdf",
    });
    const arrayBufferSpy = vi.spyOn(fakePdf, "arrayBuffer");
    const uploadInsurance = vi.fn<UploadInsurance>().mockRejectedValueOnce(
      new UploadInsuranceError({
        code: "INVALID_PDF",
        status: 422,
        userMessage: "PDF 형식이 아니에요.",
      }),
    );
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), fakePdf);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(await screen.findByText("PDF 형식 아님")).toBeInTheDocument();
    expect(screen.queryByText("읽을 수 없는 PDF")).not.toBeInTheDocument();
    expect(screen.getAllByText(/PDF 형식이 아니에요\./).length).toBeGreaterThan(
      0,
    );
    expect(uploadInsurance).toHaveBeenCalledOnce();
    expect(arrayBufferSpy).not.toHaveBeenCalled();
  });

  test("selects a PDF through drag and drop", async () => {
    renderForm();

    const dropZone = screen.getByTestId("insurance-upload-dropzone");
    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [insuranceFile],
      },
    });

    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "내 보험 분석하기" }),
      ).toBeEnabled(),
    );
  });

  test("shows a clear error when a drop contains no file", () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("insurance-upload-dropzone"), {
      dataTransfer: {
        files: [],
      },
    });

    expect(
      screen.getByText("올릴 파일을 찾지 못했어요. PDF를 다시 선택해주세요."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });

  test("selects multiple PDFs through drag and drop", async () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("insurance-upload-dropzone"), {
      dataTransfer: {
        files: [insuranceFile, secondInsuranceFile],
      },
    });

    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("2개 · 0.02 KB")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "내 보험 분석하기" }),
      ).toBeEnabled(),
    );
  });

  test("does not enforce the server file type rule in the browser", async () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("insurance-upload-dropzone"), {
      dataTransfer: {
        files: [textFile],
      },
    });

    expect(screen.getByText("note.txt")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "내 보험 분석하기" }),
      ).toBeEnabled(),
    );
  });

  test("does not enforce the server size limit in the browser", async () => {
    const user = userEvent.setup();
    const largePdf = new File(
      [new Uint8Array(10 * 1024 * 1024 + 1)],
      "large.pdf",
      {
        type: "application/pdf",
      },
    );
    renderForm();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), largePdf);

    expect(screen.getByText("large.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("uploads selected files and navigates to the analysis page", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockResolvedValueOnce({
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
          상품태그: ["질병보험", "어린이보험"],
          증권번호: "POLICY-TEST-001",
          납입기간: "20년납",
          만기일: "2027-01-01",
          보험기간: {
            시작일: "2026-01-01",
            종료일: "2027-01-01",
          },
          보험료: {
            금액: 120000,
            납입주기: "월납",
          },
        },
      })
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "test-document-id",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          계약자: "테스트고객",
          피보험자: "테스트고객",
          보험분류: "손해보험",
          상품태그: [],
        },
      });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(uploadInsurance).toHaveBeenCalledWith(
      expect.objectContaining({
        file: insuranceFile,
        portfolioSessionToken: "test-portfolio-token",
        documentId: expect.any(String),
      }),
      expect.anything(),
    );
    expect(uploadInsurance).toHaveBeenCalledWith(
      expect.objectContaining({
        file: secondInsuranceFile,
        portfolioSessionToken: "test-portfolio-token",
        documentId: expect.any(String),
      }),
      expect.anything(),
    );
    await waitFor(() => {
      expect(onAnalysisComplete).toHaveBeenCalledWith(
        expect.objectContaining({
          generatedAt: expect.any(String),
          insuranceDocuments: [
            expect.objectContaining({
              fileName: "insurance.pdf",
              result: expect.objectContaining({
                기본정보: expect.objectContaining({
                  피보험자: "테스트고객",
                  보험분류: "제3보험",
                }),
              }),
            }),
            expect.objectContaining({
              fileName: "second-insurance.pdf",
              result: expect.objectContaining({
                기본정보: expect.objectContaining({
                  피보험자: "테스트고객",
                  보험분류: "손해보험",
                }),
              }),
            }),
          ],
          selectedName: "테스트고객",
        }),
      );
    });
    expect(navigateToAnalysis).toHaveBeenCalledOnce();
  });

  test("keeps the completion beat on screen before navigating to analysis", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        계약자: "테스트고객",
        피보험자: "테스트고객",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("다 읽었어요. 결과를 보여드릴게요."),
    ).toBeVisible();
    expect(navigateToAnalysis).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(navigateToAnalysis).toHaveBeenCalledOnce();
    });
  });

  test("requires a name before saving the analysis", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    const { deleteSessionDocuments } = renderForm({
      uploadInsurance,
      onAnalysisComplete,
      navigateToAnalysis,
    });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("피보험자를 확인할 수 없는 증권이에요."),
    ).toBeInTheDocument();
    expect(screen.getByText("피보험자 미확인")).toBeInTheDocument();
    expect(
      screen.getByText(
        "피보험자를 확인할 수 없는 증권이에요. insurance.pdf 파일을 제거하고 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();
    expect(deleteSessionDocuments).toHaveBeenCalledWith(
      "test-portfolio-token",
      [expect.any(String)],
    );
  });

  test("does not fall back to the contract holder when insured person is missing", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        계약자: "테스트고객",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("피보험자를 확인할 수 없는 증권이에요."),
    ).toBeInTheDocument();
    expect(screen.getByText("피보험자 미확인")).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();
  });

  test("does not claim success when uploaded document cleanup fails", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    const deleteSessionDocuments = vi
      .fn()
      .mockRejectedValueOnce(new Error("cleanup failed"))
      .mockResolvedValue(undefined);
    renderForm({
      uploadInsurance,
      onAnalysisComplete,
      navigateToAnalysis,
      deleteSessionDocuments,
    });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "업로드한 문서를 정리하지 못했어요. 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(deleteSessionDocuments).toHaveBeenCalledWith(
      "test-portfolio-token",
      [expect.any(String)],
    );
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();

    const failedCleanupIds = deleteSessionDocuments.mock.calls[0]?.[1];
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));
    await waitFor(() => {
      expect(deleteSessionDocuments.mock.calls[1]?.[1]).toEqual(
        failedCleanupIds,
      );
    });
  });

  test("lets the user choose one name when uploaded insuranceDocuments have different names", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "document-a",
        문자수: 32,
        기본정보: {
          보험사: "삼성화재",
          상품명: "건강보험",
          계약자: "테스트고객",
          피보험자: "테스트고객",
          보험분류: "제3보험",
          상품태그: ["질병보험"],
        },
      })
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "document-b",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          계약자: "테스트고객B",
          피보험자: "테스트고객B",
          보험분류: "손해보험",
          상품태그: [],
        },
      });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    const { deleteSessionDocuments } = renderForm({
      uploadInsurance,
      onAnalysisComplete,
      navigateToAnalysis,
    });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("피보험자가 여러 명 있어요"),
    ).toBeInTheDocument();
    expect(screen.getByText("테스트고객")).toBeInTheDocument();
    expect(screen.getByText("테스트고객B")).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(screen.getByLabelText("PDF 파일 선택")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "insurance.pdf 제거" }),
    ).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: /테스트고객B/ }));
    await user.click(
      screen.getByRole("button", { name: "선택한 피보험자로 보기" }),
    );

    await waitFor(() => {
      expect(deleteSessionDocuments).toHaveBeenCalledWith(
        "test-portfolio-token",
        [expect.any(String)],
      );
      expect(onAnalysisComplete).toHaveBeenCalledWith(
        expect.objectContaining({
          selectedName: "테스트고객B",
          insuranceDocuments: [
            expect.objectContaining({
              fileName: "second-insurance.pdf",
              result: expect.objectContaining({
                기본정보: expect.objectContaining({ 피보험자: "테스트고객B" }),
              }),
            }),
          ],
        }),
      );
    });
    expect(navigateToAnalysis).toHaveBeenCalledOnce();
  });

  test("keeps the completion beat visible before navigating after choosing a name", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "document-a",
        문자수: 32,
        기본정보: {
          보험사: "삼성화재",
          상품명: "건강보험",
          계약자: "테스트고객",
          피보험자: "테스트고객",
          보험분류: "제3보험",
          상품태그: ["질병보험"],
        },
      })
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "document-b",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          계약자: "테스트고객B",
          피보험자: "테스트고객B",
          보험분류: "손해보험",
          상품태그: [],
        },
      });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("피보험자가 여러 명 있어요"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /테스트고객B/ }));
    await user.click(
      screen.getByRole("button", { name: "선택한 피보험자로 보기" }),
    );

    expect(
      await screen.findByText("다 읽었어요. 결과를 보여드릴게요."),
    ).toBeVisible();
    expect(
      screen.queryByText("피보험자가 여러 명 있어요"),
    ).not.toBeInTheDocument();
    expect(navigateToAnalysis).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(navigateToAnalysis).toHaveBeenCalledOnce();
    });
  });

  test("shows backend error details when upload fails", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockRejectedValue(new Error("파일을 분석할 수 없습니다."));
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("파일을 분석할 수 없습니다."),
    ).toBeInTheDocument();
  });

  test("shows unreadable PDFs in the selected list and lets the user remove only those files", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockRejectedValueOnce(
        new UploadInsuranceError({
          code: "PDF_TEXT_EXTRACTION_FAILED",
          status: 422,
          userMessage: "PDF에서 텍스트를 추출할 수 없습니다.",
        }),
      )
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "test-document-id",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          피보험자: "테스트고객",
          보험분류: "손해보험",
          상품태그: ["자동차보험"],
        },
      })
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "test-document-id",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          피보험자: "테스트고객",
          보험분류: "손해보험",
          상품태그: ["자동차보험"],
        },
      });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    const { deleteSessionDocuments } = renderForm({
      uploadInsurance,
      onAnalysisComplete,
      navigateToAnalysis,
    });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(await screen.findByText("읽을 수 없는 PDF")).toBeInTheDocument();
    expect(
      screen.getByText(
        "텍스트를 추출할 수 없는 PDF가 있어요. 표시된 파일을 제거한 뒤 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(deleteSessionDocuments).toHaveBeenCalledWith(
      "test-portfolio-token",
      [expect.any(String), expect.any(String)],
    );

    await user.click(
      screen.getByRole("button", { name: "insurance.pdf 제거" }),
    );
    expect(screen.queryByText("insurance.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    await waitFor(() => {
      expect(onAnalysisComplete).toHaveBeenCalledWith(
        expect.objectContaining({
          insuranceDocuments: [
            expect.objectContaining({ fileName: "second-insurance.pdf" }),
          ],
          selectedName: "테스트고객",
        }),
      );
    });
    expect(navigateToAnalysis).toHaveBeenCalledOnce();
  });

  test("asks for a password right after selecting an encrypted PDF, before submitting", async () => {
    const user = userEvent.setup();
    vi.mocked(isPdfPasswordProtected).mockResolvedValueOnce(true);
    const uploadInsurance = vi.fn<UploadInsurance>();
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);

    expect(await screen.findByText("비밀번호 필요")).toBeInTheDocument();
    expect(screen.getByLabelText("PDF 비밀번호")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
    expect(uploadInsurance).not.toHaveBeenCalled();
  });

  test("blocks submit while the password pre-check is still running", async () => {
    const user = userEvent.setup();
    vi.mocked(isPdfPasswordProtected).mockReturnValue(new Promise(() => {}));
    renderForm();

    await user.upload(
      screen.getByLabelText("PDF 파일 선택"),
      new File(["x"], "insurance.pdf", { type: "application/pdf" }),
    );

    expect(screen.getByText("확인 중")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });

  test("unlocks submit when the password pre-check fails", async () => {
    const user = userEvent.setup();
    vi.mocked(isPdfPasswordProtected).mockRejectedValue(
      new Error("pdf worker unavailable"),
    );
    renderForm();

    await user.upload(
      screen.getByLabelText("PDF 파일 선택"),
      new File(["x"], "insurance.pdf", { type: "application/pdf" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("확인 중")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("lets the user type a password and submit once the pre-check flags an encrypted PDF", async () => {
    const user = userEvent.setup();
    vi.mocked(isPdfPasswordProtected).mockResolvedValueOnce(true);
    renderForm();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);

    expect(await screen.findByText("비밀번호 필요")).toBeInTheDocument();
    await user.type(screen.getByLabelText("PDF 비밀번호"), "900101");

    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("asks for a password only for encrypted PDFs and retries with it", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockRejectedValueOnce(
        new UploadInsuranceError({
          code: "PDF_PASSWORD_REQUIRED",
          status: 422,
          userMessage: "PDF 비밀번호를 입력해주세요.",
        }),
      )
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "test-document-id",
        문자수: 20,
        기본정보: {
          보험사: "삼성화재",
          상품명: "건강보험",
          피보험자: "테스트고객",
          보험분류: "제3보험",
          상품태그: ["질병보험"],
        },
      });
    const onAnalysisComplete = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(await screen.findByText("비밀번호 필요")).toBeInTheDocument();
    expect(screen.getByLabelText("PDF 비밀번호")).toBeInTheDocument();
    expect(
      screen.getByText(/입력한 비밀번호는 저장하지 않아요\./),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "비밀번호가 필요한 PDF가 있어요. 표시된 파일에 비밀번호를 입력한 뒤 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();

    await user.type(screen.getByLabelText("PDF 비밀번호"), "900101");
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    await waitFor(() => {
      expect(uploadInsurance).toHaveBeenLastCalledWith(
        expect.objectContaining({
          file: insuranceFile,
          documentId: expect.any(String),
          password: "900101",
          portfolioSessionToken: "test-portfolio-token",
        }),
        expect.anything(),
      );
    });
    await waitFor(() => {
      expect(onAnalysisComplete).toHaveBeenCalledWith(
        expect.objectContaining({ selectedName: "테스트고객" }),
      );
    });
  });

  test("keeps network errors as a global upload error", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockRejectedValue(
      new UploadInsuranceError({
        code: "UPLOAD_NETWORK_ERROR",
        userMessage: "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
      }),
    );
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("읽을 수 없는 PDF")).not.toBeInTheDocument();
  });

  test("rolls back an already-succeeded upload when another file in the batch times out, and clears the in-flight state", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockImplementation(async (input) => {
        if (input.file === secondInsuranceFile) {
          // A stalled connection surfaces through api.ts as the same
          // UPLOAD_NETWORK_ERROR a plain connection failure produces.
          throw new UploadInsuranceError({
            code: "UPLOAD_NETWORK_ERROR",
            userMessage: "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
          });
        }
        return {
          ...POLICY_PARSE_RESPONSE_DEFAULTS,
          status: "accepted",
          documentId: "document-a",
          문자수: 32,
          기본정보: {
            보험사: "삼성화재",
            상품명: "건강보험",
            계약자: "테스트고객",
            피보험자: "테스트고객",
            보험분류: "제3보험",
            상품태그: [],
          },
        };
      });
    const { deleteSessionDocuments } = renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();

    // The already-succeeded document must be rolled back, not left orphaned
    // server-side, exactly like any other unexpected upload failure. Both
    // pre-assigned document ids are cleaned up, since the batch reserves an
    // id per file up front.
    await waitFor(() => {
      expect(deleteSessionDocuments).toHaveBeenCalledWith(
        "test-portfolio-token",
        [expect.any(String), expect.any(String)],
      );
    });

    // isAnalyzing must resolve to false so the form (and, in the modal
    // surface, its close controls) become interactive again.
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("rejects duplicate policies in the same upload batch", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        증권번호: "POLICY-TEST-001",
        피보험자: "테스트고객",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });
    const onAnalysisComplete = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "이미 올린 보험증권이에요. second-insurance.pdf 파일을 제거하고 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("중복 증권")).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
  });

  test("marks only the duplicate selected file when selected PDFs share the same file name", async () => {
    const user = userEvent.setup();
    const duplicateNamedFile = new File(["%PDF-1.7\nexisting"], "policy.pdf", {
      type: "application/pdf",
    });
    const uniqueNamedFile = new File(["%PDF-1.7\nunique"], "policy.pdf", {
      type: "application/pdf",
    });
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "test-document-id",
        문자수: 20,
        기본정보: {
          보험사: "삼성화재",
          상품명: "건강보험",
          증권번호: "POLICY-TEST-999",
          피보험자: "테스트고객",
          보험분류: "제3보험",
          상품태그: ["질병보험"],
        },
      })
      .mockResolvedValueOnce({
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        status: "accepted",
        documentId: "test-document-id",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          증권번호: "POLICY-TEST-NEW",
          피보험자: "테스트고객",
          보험분류: "손해보험",
          상품태그: ["자동차보험"],
        },
      });
    const existingDocuments: AnalyzedInsurance[] = [
      {
        id: "existing-policy",
        fileName: "existing-policy.pdf",
        result: {
          ...POLICY_RESULT_DEFAULTS,
          status: "accepted",
          문자수: 20,
          기본정보: {
            보험사: "삼성화재",
            상품명: "건강보험",
            증권번호: "POLICY-TEST-999",
            피보험자: "테스트고객",
            보험분류: "제3보험",
            상품태그: ["질병보험"],
          },
        },
      },
    ];
    const onAnalysisComplete = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, existingDocuments });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      duplicateNamedFile,
      uniqueNamedFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "이미 올린 보험증권이에요. policy.pdf 파일을 제거하고 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("policy.pdf")).toHaveLength(2);
    expect(screen.getAllByText("중복 증권")).toHaveLength(1);
    expect(screen.getAllByText("이미 올린 보험증권이에요.")).toHaveLength(1);
    expect(onAnalysisComplete).not.toHaveBeenCalled();
  });

  test("rejects the same PDF file even when policy fields are not enough for identity matching", async () => {
    const user = userEvent.setup();
    const samePdfAgain = new File(["%PDF-1.7"], "same-policy-copy.pdf", {
      type: "application/pdf",
    });
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        피보험자: "테스트고객",
        보험분류: "미분류",
        상품태그: [],
      },
    });
    const onAnalysisComplete = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      samePdfAgain,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "이미 올린 보험증권이에요. same-policy-copy.pdf 파일을 제거하고 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(uploadInsurance).toHaveBeenCalledTimes(2);
    expect(onAnalysisComplete).not.toHaveBeenCalled();
  });

  test("rejects a byte-identical re-upload after server acceptance", async () => {
    const user = userEvent.setup();
    const fingerprintOf = async (file: File) => {
      const buffer = await file.arrayBuffer();
      const digest = await crypto.subtle.digest("SHA-256", buffer);
      return Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    };
    const existingDocuments: AnalyzedInsurance[] = [
      {
        id: "existing-policy",
        fileName: "existing-policy.pdf",
        fileFingerprint: await fingerprintOf(insuranceFile),
        result: {
          ...POLICY_RESULT_DEFAULTS,
          status: "accepted",
          문자수: 20,
          기본정보: {
            보험사: "삼성화재",
            상품명: "건강보험",
            피보험자: "테스트고객",
            보험분류: "제3보험",
            상품태그: ["질병보험"],
          },
        },
      },
    ];
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        피보험자: "테스트고객",
        보험분류: "미분류",
        상품태그: [],
      },
    });
    const onAnalysisComplete = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, existingDocuments });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "이미 올린 보험증권이에요. insurance.pdf 파일을 제거하고 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(uploadInsurance).toHaveBeenCalledOnce();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
  });

  test("disables upload while a request is pending", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(
            () =>
              resolve({
                ...POLICY_PARSE_RESPONSE_DEFAULTS,
                status: "accepted",
                documentId: "test-document-id",
                문자수: 32,
                기본정보: {
                  보험사: "삼성화재",
                  피보험자: "테스트고객",
                  보험분류: "제3보험",
                  상품태그: ["질병보험"],
                  만기일: "2027-01-01",
                },
              }),
            50,
          );
        }),
    );
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      screen.queryByRole("button", { name: "내 보험 분석하기" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("증권을 한 장씩 읽고 있어요")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "보험 분석 진행률" }));
  });

  test("shows reassurance notes next to the dropzone", () => {
    renderForm();

    expect(screen.getByText("개인정보는 가려서 처리해요")).toBeInTheDocument();
    expect(
      screen.getByText("가입 권유 전화가 가지 않아요"),
    ).toBeInTheDocument();
  });

  test("default behavior writes the analysis into context and navigates client-side", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      status: "accepted",
      documentId: "test-document-id",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        계약자: "테스트고객",
        피보험자: "테스트고객",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });
    const originalLocation = window.location;
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignSpy },
    });

    renderWithProviders(
      <>
        <InsuranceUploadForm
          uploadInsurance={uploadInsurance}
          createSession={createSession}
        />
        <InsuranceDataProbe />
      </>,
    );

    expect(screen.getByTestId("probe")).toHaveTextContent("");

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    // The default onAnalysisComplete must write the uploaded document into the
    // in-memory context; the probe reflects that write.
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("insurance.pdf");
    });
    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/analysis");
    });
    expect(screen.getByText("증권을 한 장씩 읽고 있어요")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "내 보험 분석하기" }),
    ).not.toBeInTheDocument();
    expect(assignSpy).not.toHaveBeenCalled();

    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  test("shows per-file reading status and grounding note while analyzing", async () => {
    const user = userEvent.setup();
    let resolveFirstUpload: (() => void) | undefined;
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirstUpload = () =>
              resolve({
                ...POLICY_PARSE_RESPONSE_DEFAULTS,
                status: "accepted",
                documentId: "test-document-id",
                문자수: 32,
                기본정보: {
                  보험사: "삼성화재",
                  피보험자: "테스트고객",
                  보험분류: "제3보험",
                  상품태그: ["질병보험"],
                },
              });
          }),
      )
      .mockImplementationOnce(() => new Promise(() => {}));
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(screen.getByText("보통 1~2분 정도 걸려요")).toBeInTheDocument();
    expect(
      screen.getByText("확인이 안 되는 내용은 추측하지 않아요."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("읽는 중")).toHaveLength(2);

    await act(async () => {
      resolveFirstUpload?.();
    });

    expect(await screen.findByText("완료")).toBeInTheDocument();
    expect(screen.getAllByText("읽는 중")).toHaveLength(1);
    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();
  });
});
