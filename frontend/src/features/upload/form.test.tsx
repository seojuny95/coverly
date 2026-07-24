import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { type UploadInsurance } from "./form";
import { UploadInsuranceError } from "./api";
import {
  createSession,
  insuranceFile,
  renderForm,
  resetFormTestState,
  routerPrefetch,
  secondInsuranceFile,
  textFile,
} from "./form.test-support";
import {
  POLICY_PARSE_RESPONSE_DEFAULTS,
  POLICY_RESULT_DEFAULTS,
} from "../../test/api-fixtures";

beforeEach(resetFormTestState);

describe("InsuranceUploadForm selection and completion", () => {
  test("shows a distinct server preparation state before reading PDFs", async () => {
    const user = userEvent.setup();
    let markServerReady: () => void = () => undefined;
    const pendingServer = new Promise<void>((resolve) => {
      markServerReady = resolve;
    });
    const prepareServer = vi.fn(() => pendingServer);
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      ...POLICY_PARSE_RESPONSE_DEFAULTS,
      documentId: "document-1",
    });
    renderForm({ prepareServer, uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText("분석 서버를 준비하고 있어요"),
    ).toBeVisible();
    expect(
      screen.getByText("처음 연결할 때는 최대 1분 정도 걸릴 수 있어요"),
    ).toBeVisible();
    expect(screen.getByText("대기 중")).toBeVisible();
    expect(createSession).not.toHaveBeenCalled();
    expect(uploadInsurance).not.toHaveBeenCalled();

    markServerReady();

    await waitFor(() => expect(createSession).toHaveBeenCalledOnce());
    await waitFor(() => expect(uploadInsurance).toHaveBeenCalledOnce());
  });

  test("cancels server preparation when the upload form unmounts", async () => {
    const user = userEvent.setup();
    let requestSignal: AbortSignal | undefined;
    const prepareServer = vi.fn((signal?: AbortSignal) => {
      requestSignal = signal;
      return new Promise<void>(() => {});
    });
    const { unmount } = renderForm({ prepareServer });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));
    await waitFor(() => expect(prepareServer).toHaveBeenCalledOnce());

    unmount();

    expect(requestSignal?.aborted).toBe(true);
  });

  test("prefetches the programmatic analysis destination", async () => {
    renderForm();

    await waitFor(() => {
      expect(routerPrefetch).toHaveBeenCalledWith("/analysis");
    });
  });

  test("shows the five-document limit before file selection", () => {
    renderForm();

    expect(screen.getByText("PDF · 최대 5개")).toBeInTheDocument();
  });

  test("shows the remaining document allowance for additional uploads", () => {
    const existingDocuments = Array.from({ length: 4 }, (_, index) => ({
      id: `existing-${index}`,
      fileName: `existing-${index}.pdf`,
      result: POLICY_RESULT_DEFAULTS,
    }));

    renderForm({ existingDocuments });

    expect(
      screen.getByText("PDF · 추가 가능 1개 · 전체 최대 5개"),
    ).toBeInTheDocument();
  });

  test("accepts five policy PDFs and rejects a sixth", async () => {
    const user = userEvent.setup();
    let activeUploads = 0;
    let maxActiveUploads = 0;
    const uploadInsurance = vi.fn<UploadInsurance>(async ({ documentId }) => {
      activeUploads += 1;
      maxActiveUploads = Math.max(maxActiveUploads, activeUploads);
      await new Promise((resolve) => setTimeout(resolve, 5));
      activeUploads -= 1;
      return {
        ...POLICY_PARSE_RESPONSE_DEFAULTS,
        documentId,
      };
    });
    renderForm({ uploadInsurance });
    const files = Array.from(
      { length: 6 },
      (_, index) =>
        new File([`%PDF-1.7 file ${index}`], `policy-${index}.pdf`, {
          type: "application/pdf",
        }),
    );

    await user.upload(screen.getByLabelText("PDF 파일 선택"), files);

    expect(
      screen.getByText(
        "보험증권은 최대 5개까지 분석할 수 있어요. 지금은 5개까지 추가할 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("선택된 PDF가 없어요.")).toBeInTheDocument();
    expect(uploadInsurance).not.toHaveBeenCalled();

    await user.upload(
      screen.getByLabelText("PDF 파일 선택"),
      files.slice(0, 5),
    );

    expect(
      screen.queryByText(
        "보험증권은 최대 5개까지 분석할 수 있어요. 지금은 5개까지 추가할 수 있어요.",
      ),
    ).not.toBeInTheDocument();
    for (const file of files.slice(0, 5)) {
      expect(screen.getByText(file.name)).toBeInTheDocument();
    }

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "내 보험 분석하기" }),
      ).toBeEnabled();
    });
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    await waitFor(() => {
      expect(uploadInsurance).toHaveBeenCalledTimes(5);
    });
    expect(maxActiveUploads).toBe(5);
  });

  test("counts existing policies toward the five-document limit", async () => {
    const user = userEvent.setup();
    const existingDocuments = Array.from({ length: 4 }, (_, index) => ({
      id: `existing-${index}`,
      fileName: `existing-${index}.pdf`,
      result: POLICY_RESULT_DEFAULTS,
    }));
    renderForm({ existingDocuments });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), [
      insuranceFile,
      secondInsuranceFile,
    ]);

    expect(
      screen.getByText(
        "보험증권은 최대 5개까지 분석할 수 있어요. 지금은 1개까지 추가할 수 있어요.",
      ),
    ).toBeInTheDocument();
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

    const trigger = screen.getByRole("button", {
      name: "보험증권을 어디서 받는지 모르겠어요",
    });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    // jsdom's accessibility-tree queries don't honor `inert`, so a collapsed
    // link is still findable by role here; assert the `inert` ancestor
    // directly to prove it is actually removed from the tab order.
    const collapsedLink = screen.getByRole("link", {
      name: "가입한 보험사 확인 (새 창에서 열기)",
    });
    expect(collapsedLink.closest("[inert]")).not.toBeNull();

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText("보험증권을 이렇게 받을 수 있어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/보험사 앱·홈페이지 → 계약 관리 또는 증명서 발급/),
    ).toBeInTheDocument();

    const insurerLookupLink = screen.getByRole("link", {
      name: "가입한 보험사 확인 (새 창에서 열기)",
    });
    expect(insurerLookupLink.closest("[inert]")).toBeNull();
    expect(insurerLookupLink).toHaveAttribute(
      "href",
      "https://cont.insure.or.kr/cont_web/intro.do",
    );
    expect(insurerLookupLink).toHaveAttribute("target", "_blank");
  });

  test("toggles the policy document guide from the keyboard", async () => {
    const user = userEvent.setup();
    renderForm();

    const trigger = screen.getByRole("button", {
      name: "보험증권을 어디서 받는지 모르겠어요",
    });
    trigger.focus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.keyboard("{Enter}");
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    await user.keyboard(" ");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
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
    expect(arrayBufferSpy).toHaveBeenCalledOnce();
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

  test("rejects an oversized PDF before reading or uploading it", async () => {
    const user = userEvent.setup();
    const largePdf = new File(["%PDF-1.7"], "large.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(largePdf, "size", {
      value: 10 * 1024 * 1024 + 1,
    });
    const arrayBufferSpy = vi.spyOn(largePdf, "arrayBuffer");
    const uploadInsurance = vi.fn<UploadInsurance>();
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), largePdf);

    expect(
      screen.getByText(
        "파일이 너무 커요. PDF 한 개당 최대 10MB까지 올릴 수 있어요.",
      ),
    ).toBeInTheDocument();
    expect(arrayBufferSpy).not.toHaveBeenCalled();
    expect(uploadInsurance).not.toHaveBeenCalled();
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

    await waitFor(() => {
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
    });
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
});
