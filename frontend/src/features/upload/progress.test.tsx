import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisProgress } from "./progress";

describe("AnalysisProgress", () => {
  it("floors the progress bar at the completed-file milestone", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 1, total: 2 }}
        files={[
          { name: "a.pdf", status: "done" },
          { name: "b.pdf", status: "reading" },
        ]}
        surface="page"
      />,
    );

    // 1 of 2 done → the bar never reads below the 50% milestone, even before
    // the trickle timer advances.
    const bar = screen.getByRole("progressbar", { name: "보험 분석 진행률" });
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeGreaterThanOrEqual(
      50,
    );
  });

  it("fully covers the previous page and keeps the analysis header mark", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 0, total: 1 }}
        files={[{ name: "a.pdf", status: "reading" }]}
        surface="page"
      />,
    );

    expect(screen.getByRole("status")).toHaveClass("bg-white");
    expect(screen.getByText(/coverly/)).toBeInTheDocument();
  });

  it("shows each file with its done/reading label", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 1, total: 2 }}
        files={[
          { name: "a.pdf", status: "done" },
          { name: "b.pdf", status: "reading" },
        ]}
        surface="page"
      />,
    );

    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText("읽는 중")).toBeInTheDocument();
  });

  it("centers a single file instead of leaving it in the first grid column", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 0, total: 1 }}
        files={[{ name: "only.pdf", status: "reading" }]}
        surface="page"
      />,
    );

    expect(screen.getByLabelText("파일별 진행 상태")).toHaveClass("max-w-md");
  });

  it("keeps the two-column grid for multiple files", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 0, total: 2 }}
        files={[
          { name: "a.pdf", status: "reading" },
          { name: "b.pdf", status: "reading" },
        ]}
        surface="page"
      />,
    );

    expect(screen.getByLabelText("파일별 진행 상태")).toHaveClass(
      "sm:grid-cols-2",
    );
  });

  it("stays at 0 with no files/progress", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 0, total: 0 }}
        files={[]}
        surface="modal"
      />,
    );
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("0");
    expect(screen.queryByLabelText("파일별 진행 상태")).not.toBeInTheDocument();
  });

  it("shows a finished state when completing", () => {
    render(
      <AnalysisProgress
        progress={{ completed: 2, total: 2 }}
        files={[
          { name: "a.pdf", status: "done" },
          { name: "b.pdf", status: "done" },
        ]}
        surface="page"
        isCompleting
      />,
    );

    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    expect(screen.getByText("다 읽었어요. 결과를 보여드릴게요.")).toBeVisible();
  });
});
