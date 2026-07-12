import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi, beforeEach } from "vitest";

import {
  InsuranceUploadForm,
  type UploadInsurance,
} from "./insurance-upload-form";
import type { InsuranceAnalysis } from "../insurance-analysis/insurance-analysis-store";
import { useInsuranceData } from "../insurance-analysis/insurance-analysis-store";
import { renderWithProviders } from "../../test-utils/render-with-providers";

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
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});
const textFile = new File(["hello"], "note.txt", {
  type: "text/plain",
});
const secondInsuranceFile = new File(["%PDF-1.7"], "second-insurance.pdf", {
  type: "application/pdf",
});

function renderForm({
  uploadInsurance = vi.fn(),
  onAnalysisComplete = vi.fn(),
  navigateToAnalysis = vi.fn(),
}: {
  uploadInsurance?: UploadInsurance;
  onAnalysisComplete?: (analysis: InsuranceAnalysis) => void;
  navigateToAnalysis?: () => void;
} = {}) {
  renderWithProviders(
    <InsuranceUploadForm
      uploadInsurance={uploadInsurance}
      onAnalysisComplete={onAnalysisComplete}
      navigateToAnalysis={navigateToAnalysis}
    />,
  );
  return { uploadInsurance, onAnalysisComplete, navigateToAnalysis };
}

beforeEach(() => {
  routerPush.mockClear();
});

describe("InsuranceUploadForm", () => {
  test("disables upload until a file is selected", () => {
    renderForm();

    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
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

  test("selects a PDF through drag and drop", async () => {
    renderForm();

    const dropZone = screen.getByTestId("insurance-upload-dropzone");
    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [insuranceFile],
      },
    });

    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
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

  test("selects multiple PDFs through drag and drop", () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("insurance-upload-dropzone"), {
      dataTransfer: {
        files: [insuranceFile, secondInsuranceFile],
      },
    });

    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("2개 · 0.02 KB")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("rejects non-PDF files before upload", async () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("insurance-upload-dropzone"), {
      dataTransfer: {
        files: [textFile],
      },
    });

    expect(screen.getByText("PDF 파일만 올릴 수 있어요.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });

  test("rejects files larger than 10MB before upload", async () => {
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

    expect(
      screen.getByText("파일이 너무 커요. 최대 10MB까지 올릴 수 있어요."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });

  test("uploads selected files and navigates to the analysis page", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockResolvedValueOnce({
        status: "accepted",
        문자수: 32,
        기본정보: {
          보험사: "삼성화재",
          상품명: "건강보험",
          계약자: "테스트고객",
          피보험자: "테스트고객",
          보험분류: "상해·질병·실손",
          상품태그: ["질병", "어린이"],
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
        status: "accepted",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          계약자: "테스트고객",
          피보험자: "테스트고객",
          보험분류: "자동차",
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
      insuranceFile,
      expect.anything(),
    );
    expect(uploadInsurance).toHaveBeenCalledWith(
      secondInsuranceFile,
      expect.anything(),
    );
    expect(onAnalysisComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        generatedAt: expect.any(String),
        insuranceDocuments: [
          expect.objectContaining({
            fileName: "insurance.pdf",
            result: expect.objectContaining({
              기본정보: expect.objectContaining({
                피보험자: "테스트고객",
                보험분류: "상해·질병·실손",
              }),
            }),
          }),
          expect.objectContaining({
            fileName: "second-insurance.pdf",
            result: expect.objectContaining({
              기본정보: expect.objectContaining({
                피보험자: "테스트고객",
                보험분류: "자동차",
              }),
            }),
          }),
        ],
        selectedName: "테스트고객",
      }),
    );
    expect(navigateToAnalysis).toHaveBeenCalledOnce();
  });

  test("requires a name before saving the analysis", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      status: "accepted",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        보험분류: "상해·질병·실손",
        상품태그: ["질병"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "피보험자를 확인할 수 없는 증권이 있어요. 피보험자가 확인된 증권만 분석할 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();
  });

  test("does not fall back to the contract holder when insured person is missing", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      status: "accepted",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        계약자: "테스트고객",
        보험분류: "상해·질병·실손",
        상품태그: ["질병"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadInsurance, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "피보험자를 확인할 수 없는 증권이 있어요. 피보험자가 확인된 증권만 분석할 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();
  });

  test("lets the user choose one name when uploaded insuranceDocuments have different names", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockResolvedValueOnce({
        status: "accepted",
        문자수: 32,
        기본정보: {
          보험사: "삼성화재",
          상품명: "건강보험",
          계약자: "테스트고객",
          피보험자: "테스트고객",
          보험분류: "상해·질병·실손",
          상품태그: ["질병"],
        },
      })
      .mockResolvedValueOnce({
        status: "accepted",
        문자수: 20,
        기본정보: {
          보험사: "현대해상화재보험",
          상품명: "개인용자동차보험",
          계약자: "테스트고객B",
          피보험자: "테스트고객B",
          보험분류: "자동차",
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
    expect(screen.getByText("테스트고객")).toBeInTheDocument();
    expect(screen.getByText("테스트고객B")).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("radio", { name: /테스트고객B/ }));
    await user.click(
      screen.getByRole("button", { name: "선택한 피보험자로 보기" }),
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
    expect(navigateToAnalysis).toHaveBeenCalledOnce();
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

  test("disables upload while a request is pending", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(
            () =>
              resolve({
                status: "accepted",
                문자수: 32,
                기본정보: {
                  보험사: "삼성화재",
                  피보험자: "테스트고객",
                  보험분류: "상해·질병·실손",
                  상품태그: ["질병"],
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
      status: "accepted",
      문자수: 20,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        계약자: "테스트고객",
        피보험자: "테스트고객",
        보험분류: "상해·질병·실손",
        상품태그: ["질병"],
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
        <InsuranceUploadForm uploadInsurance={uploadInsurance} />
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
                status: "accepted",
                문자수: 32,
                기본정보: {
                  보험사: "삼성화재",
                  피보험자: "테스트고객",
                  보험분류: "상해·질병·실손",
                  상품태그: ["질병"],
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

    resolveFirstUpload?.();

    expect(await screen.findByText("완료")).toBeInTheDocument();
    expect(screen.getAllByText("읽는 중")).toHaveLength(1);
    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();
  });
});
