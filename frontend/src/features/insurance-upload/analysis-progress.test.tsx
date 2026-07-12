import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisProgress } from "./analysis-progress";

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
});
