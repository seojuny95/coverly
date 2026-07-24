import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { type UploadInsurance } from "./form";
import { UploadInsuranceError } from "./api";
import {
  createSession,
  insuranceFile,
  passwordProtectedMock,
  renderDefaultForm,
  renderForm,
  resetFormTestState,
  routerPush,
  secondInsuranceFile,
} from "./form.test-support";
import type { AnalyzedInsurance } from "../analysis/store";
import {
  POLICY_PARSE_RESPONSE_DEFAULTS,
  POLICY_RESULT_DEFAULTS,
} from "../../test/api-fixtures";

beforeEach(resetFormTestState);

describe("InsuranceUploadForm failures and upload lifecycle", () => {
  test("does not expose an unexpected internal error message", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockRejectedValue(new Error("파일을 분석할 수 없습니다."));
    renderForm({ uploadInsurance });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "업로드에 실패했어요. 잠시 후 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("파일을 분석할 수 없습니다."),
    ).not.toBeInTheDocument();
  });

  test("shows unreadable PDFs in the selected list and lets the user remove only those files", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi
      .fn<UploadInsurance>()
      .mockRejectedValueOnce(
        new UploadInsuranceError({
          code: "PDF_TEXT_EXTRACTION_FAILED",
          status: 422,
          userMessage: "PDF에서 텍스트를 추출할 수 없어요.",
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
        "일부 PDF를 읽지 못했어요. 표시된 파일의 안내를 확인한 뒤 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("insurance.pdf")).toBeInTheDocument();
    expect(screen.getByText("second-insurance.pdf")).toBeInTheDocument();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
    expect(deleteSessionDocuments).toHaveBeenCalledWith(
      "test-portfolio-token",
      [expect.any(String)],
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
    passwordProtectedMock.mockResolvedValueOnce(true);
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
    passwordProtectedMock.mockReturnValue(new Promise(() => {}));
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
    passwordProtectedMock.mockRejectedValue(
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
    passwordProtectedMock.mockResolvedValueOnce(true);
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

  test("marks the analysis session expired when an additional upload is rejected by the session boundary", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockRejectedValue(
      new UploadInsuranceError({
        code: "INVALID_PORTFOLIO_SESSION",
        status: 403,
        userMessage: "분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
      }),
    );
    const deleteSessionDocuments = vi.fn().mockResolvedValue(undefined);

    renderForm({
      uploadInsurance,
      deleteSessionDocuments,
      initialAnalysis: {
        generatedAt: "2026-07-23T00:00:00.000Z",
        selectedName: "테스트고객",
        portfolioSessionToken: "expired-portfolio-token",
        portfolioSessionExpiresAt: "2026-07-23T00:00:00.000Z",
        counselTurnsRemaining: 10,
        insuranceDocuments: [
          {
            id: "existing-document",
            fileName: "existing.pdf",
            result: {
              ...POLICY_RESULT_DEFAULTS,
              기본정보: {
                피보험자: "테스트고객",
                보험분류: "제3보험",
                상품태그: [],
              },
            },
          },
        ],
      },
    });

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "내 보험 분석하기" }));

    expect(
      await screen.findByText(
        "분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("session-expired")).toHaveTextContent("yes");
    expect(deleteSessionDocuments).not.toHaveBeenCalled();
    expect(createSession).not.toHaveBeenCalled();
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
    expect(uploadInsurance).not.toHaveBeenCalled();
    expect(onAnalysisComplete).not.toHaveBeenCalled();
  });

  test("rejects a byte-identical re-upload before server processing", async () => {
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
    expect(uploadInsurance).not.toHaveBeenCalled();
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

    renderDefaultForm(uploadInsurance);

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
