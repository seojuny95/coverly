import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SelectedFileList } from "./selected-file-list";
import type { SelectedUploadFile } from "./upload-types";

function file(
  overrides: Partial<SelectedUploadFile> & { id: string; name: string },
): SelectedUploadFile {
  const { name, ...rest } = overrides;
  return {
    status: "idle",
    ...rest,
    file: new File(["%PDF-1.7"], name, { type: "application/pdf" }),
  };
}

describe("SelectedFileList", () => {
  it("shows an empty message with no files", () => {
    render(
      <SelectedFileList
        files={[]}
        surface="page"
        onRemove={vi.fn()}
        disableRemove={false}
      />,
    );
    expect(screen.getByText("선택된 PDF가 없어요.")).toBeInTheDocument();
  });

  it("renders each file and reports removals", () => {
    const onRemove = vi.fn();
    render(
      <SelectedFileList
        files={[
          file({ id: "1", name: "a.pdf" }),
          file({ id: "2", name: "b.pdf" }),
        ]}
        surface="page"
        onRemove={onRemove}
        disableRemove={false}
      />,
    );

    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
    expect(screen.getByText(/2개/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "a.pdf 제거" }));
    expect(onRemove).toHaveBeenCalledWith("1");
  });

  it("labels a failed file by its error code, not a generic message", () => {
    render(
      <SelectedFileList
        files={[
          file({
            id: "1",
            name: "not-pdf.pdf",
            status: "failed",
            errorCode: "INVALID_PDF",
            errorMessage: "PDF 형식이 아니에요.",
          }),
        ]}
        surface="page"
        onRemove={vi.fn()}
        disableRemove={false}
      />,
    );
    expect(screen.getByText("PDF 형식 아님")).toBeInTheDocument();
    expect(screen.queryByText("읽을 수 없는 PDF")).not.toBeInTheDocument();
  });

  it("disables remove buttons when disableRemove is set", () => {
    render(
      <SelectedFileList
        files={[file({ id: "1", name: "a.pdf" })]}
        surface="page"
        onRemove={vi.fn()}
        disableRemove
      />,
    );
    expect(screen.getByRole("button", { name: "a.pdf 제거" })).toBeDisabled();
  });
});
