import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { UploadForm, type UploadPolicy } from "./upload-form";
import type { PolicyAnalysis } from "../policy-analysis/analysis-store";

const policyFile = new File(["%PDF-1.7"], "policy.pdf", {
  type: "application/pdf",
});
const textFile = new File(["hello"], "note.txt", {
  type: "text/plain",
});
const secondPolicyFile = new File(["%PDF-1.7"], "second-policy.pdf", {
  type: "application/pdf",
});

function renderForm({
  uploadPolicy = vi.fn(),
  onAnalysisComplete = vi.fn(),
  navigateToAnalysis = vi.fn(),
}: {
  uploadPolicy?: UploadPolicy;
  onAnalysisComplete?: (analysis: PolicyAnalysis) => void;
  navigateToAnalysis?: () => void;
} = {}) {
  render(
    <UploadForm
      uploadPolicy={uploadPolicy}
      onAnalysisComplete={onAnalysisComplete}
      navigateToAnalysis={navigateToAnalysis}
    />,
  );
  return { uploadPolicy, onAnalysisComplete, navigateToAnalysis };
}

describe("UploadForm", () => {
  test("disables upload until a file is selected", () => {
    renderForm();

    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeDisabled();
  });

  test("selects a PDF through the file picker", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);

    expect(screen.getByText("policy.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("selects a PDF through drag and drop", async () => {
    renderForm();

    const dropZone = screen.getByTestId("policy-upload-dropzone");
    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [policyFile],
      },
    });

    expect(screen.getByText("policy.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("shows a clear error when a drop contains no file", () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("policy-upload-dropzone"), {
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

    fireEvent.drop(screen.getByTestId("policy-upload-dropzone"), {
      dataTransfer: {
        files: [policyFile, secondPolicyFile],
      },
    });

    expect(screen.getByText("policy.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-policy.pdf")).toBeInTheDocument();
    expect(screen.getByText("2개 · 0.02 KB")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "내 보험 분석하기" }),
    ).toBeEnabled();
  });

  test("rejects non-PDF files before upload", async () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("policy-upload-dropzone"), {
      dataTransfer: {
        files: [textFile],
      },
    });

    expect(
      screen.getByText("PDF 파일만 올릴 수 있어요."),
    ).toBeInTheDocument();
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
    const uploadPolicy = vi
      .fn<UploadPolicy>()
      .mockResolvedValueOnce({
        status: "accepted",
        문자수: 32,
        문서판정: {
          보험증권추정: true,
          점수: 7,
          근거: ["보험증권", "증권번호"],
        },
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
        문서판정: {
          보험증권추정: true,
          점수: 6,
          근거: ["보험증권"],
        },
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
    renderForm({ uploadPolicy, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      policyFile,
      secondPolicyFile,
    ]);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(uploadPolicy).toHaveBeenCalledWith(policyFile);
    expect(uploadPolicy).toHaveBeenCalledWith(secondPolicyFile);
    expect(onAnalysisComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        generatedAt: expect.any(String),
        policies: [
          expect.objectContaining({
            fileName: "policy.pdf",
            result: expect.objectContaining({
              기본정보: expect.objectContaining({
                피보험자: "테스트고객",
                보험분류: "상해·질병·실손",
              }),
            }),
          }),
          expect.objectContaining({
            fileName: "second-policy.pdf",
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
    const uploadPolicy = vi.fn<UploadPolicy>().mockResolvedValue({
      status: "accepted",
      문자수: 20,
      문서판정: {
        보험증권추정: true,
        점수: 6,
        근거: ["보험증권"],
      },
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        보험분류: "상해·질병·실손",
        상품태그: ["질병"],
      },
    });
    const onAnalysisComplete = vi.fn();
    const navigateToAnalysis = vi.fn();
    renderForm({ uploadPolicy, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "피보험자를 확인할 수 없는 증권이 있어요. 피보험자가 확인된 증권만 분석할 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();
  });

  test("does not fall back to the policy holder when insured person is missing", async () => {
    const user = userEvent.setup();
    const uploadPolicy = vi.fn<UploadPolicy>().mockResolvedValue({
      status: "accepted",
      문자수: 20,
      문서판정: {
        보험증권추정: true,
        점수: 6,
        근거: ["보험증권"],
      },
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
    renderForm({ uploadPolicy, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "피보험자를 확인할 수 없는 증권이 있어요. 피보험자가 확인된 증권만 분석할 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(navigateToAnalysis).not.toHaveBeenCalled();
  });

  test("lets the user choose one name when uploaded policies have different names", async () => {
    const user = userEvent.setup();
    const uploadPolicy = vi
      .fn<UploadPolicy>()
      .mockResolvedValueOnce({
        status: "accepted",
        문자수: 32,
        문서판정: {
          보험증권추정: true,
          점수: 7,
          근거: ["보험증권"],
        },
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
        문서판정: {
          보험증권추정: true,
          점수: 6,
          근거: ["보험증권"],
        },
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
    renderForm({ uploadPolicy, onAnalysisComplete, navigateToAnalysis });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      policyFile,
      secondPolicyFile,
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
        policies: [
          expect.objectContaining({
            fileName: "second-policy.pdf",
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
    const uploadPolicy = vi
      .fn<UploadPolicy>()
      .mockRejectedValue(new Error("보험증권으로 확인할 수 없습니다."));
    renderForm({ uploadPolicy });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("보험증권으로 확인할 수 없습니다."),
    ).toBeInTheDocument();
  });

  test("disables upload while a request is pending", async () => {
    const user = userEvent.setup();
    const uploadPolicy = vi.fn<UploadPolicy>().mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(
            () =>
              resolve({
                status: "accepted",
                문자수: 32,
                문서판정: {
                  보험증권추정: true,
                  점수: 7,
                  근거: ["보험증권"],
                },
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
    renderForm({ uploadPolicy });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      screen.queryByRole("button", { name: "내 보험 분석하기" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("보험을 정리하고 있어요")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "보험 분석 진행률" }));
  });
});
