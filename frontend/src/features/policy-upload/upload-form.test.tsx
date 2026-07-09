import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { UploadForm, type UploadPolicy } from "./upload-form";

const policyFile = new File(["%PDF-1.7"], "policy.pdf", {
  type: "application/pdf",
});
const textFile = new File(["hello"], "note.txt", {
  type: "text/plain",
});

function renderForm(uploadPolicy: UploadPolicy = vi.fn()) {
  render(<UploadForm uploadPolicy={uploadPolicy} />);
}

describe("UploadForm", () => {
  test("disables upload until a file is selected", () => {
    renderForm();

    expect(screen.getByRole("button", { name: "업로드" })).toBeDisabled();
  });

  test("selects a PDF through the file picker", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);

    expect(screen.getByText("policy.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업로드" })).toBeEnabled();
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
    expect(screen.getByRole("button", { name: "업로드" })).toBeEnabled();
  });

  test("shows a clear error when a drop contains no file", () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("policy-upload-dropzone"), {
      dataTransfer: {
        files: [],
      },
    });

    expect(
      screen.getByText("업로드할 파일을 찾을 수 없습니다."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업로드" })).toBeDisabled();
  });

  test("rejects multiple dropped files", () => {
    const secondPolicyFile = new File(["%PDF-1.7"], "second-policy.pdf", {
      type: "application/pdf",
    });
    renderForm();

    fireEvent.drop(screen.getByTestId("policy-upload-dropzone"), {
      dataTransfer: {
        files: [policyFile, secondPolicyFile],
      },
    });

    expect(
      screen.getByText("PDF 파일은 하나만 업로드할 수 있습니다."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업로드" })).toBeDisabled();
  });

  test("rejects non-PDF files before upload", async () => {
    renderForm();

    fireEvent.drop(screen.getByTestId("policy-upload-dropzone"), {
      dataTransfer: {
        files: [textFile],
      },
    });

    expect(
      screen.getByText("PDF 파일만 업로드할 수 있습니다."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업로드" })).toBeDisabled();
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
      screen.getByText("파일이 너무 큽니다 (최대 10MB)."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업로드" })).toBeDisabled();
  });

  test("uploads the selected file and shows a simple completion state", async () => {
    const user = userEvent.setup();
    const uploadPolicy = vi.fn<UploadPolicy>().mockResolvedValue({
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
    });
    renderForm(uploadPolicy);

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "업로드" }));

    expect(uploadPolicy).toHaveBeenCalledWith(policyFile);
    expect(
      await screen.findByText("업로드가 완료되었습니다."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("다음 단계에서 보장 내용을 읽습니다."),
    ).toBeInTheDocument();
    expect(screen.getByText("삼성화재")).toBeInTheDocument();
    expect(screen.getByText("건강보험")).toBeInTheDocument();
    expect(screen.getByText("상해·질병·실손")).toBeInTheDocument();
    expect(screen.getByText("질병, 어린이")).toBeInTheDocument();
    expect(screen.getByText("POLICY-TEST-001")).toBeInTheDocument();
    expect(screen.getByText("20년납")).toBeInTheDocument();
    expect(screen.getByText("2027-01-01")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 - 2027-01-01")).toBeInTheDocument();
    expect(screen.getByText("월납 120,000원")).toBeInTheDocument();
    expect(screen.queryByText("Verification")).not.toBeInTheDocument();
    expect(screen.queryByText("보험증권, 증권번호")).not.toBeInTheDocument();
  });

  test("shows backend error details when upload fails", async () => {
    const user = userEvent.setup();
    const uploadPolicy = vi
      .fn<UploadPolicy>()
      .mockRejectedValue(new Error("보험증권으로 확인할 수 없습니다."));
    renderForm(uploadPolicy);

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "업로드" }));

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
                  보험분류: "상해·질병·실손",
                  상품태그: ["질병"],
                  만기일: "2027-01-01",
                },
              }),
            50,
          );
        }),
    );
    renderForm(uploadPolicy);

    await user.upload(screen.getByLabelText("PDF 파일 선택"), policyFile);
    await user.click(screen.getByRole("button", { name: "업로드" }));

    expect(screen.getByRole("button", { name: "업로드 중" })).toBeDisabled();
  });
});
