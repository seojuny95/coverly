import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadOptions } from "./upload-options";
import { createSamplePortfolioSession } from "../analysis/session/api";
import { useInsuranceData } from "../analysis/session/store";
import { renderWithProviders } from "../../test/render-with-providers";
import { POLICY_PARSE_RESPONSE_DEFAULTS } from "../../test/api-fixtures";
import { waitForBackendReady } from "@/shared/api/readiness";

const routerPush = vi.hoisted(() => vi.fn());

vi.mock("./form/upload-form", () => ({
  PolicyUploadForm: ({
    onInteractionLockedChange,
  }: {
    onInteractionLockedChange?: (isInteractionLocked: boolean) => void;
  }) => (
    <button type="button" onClick={() => onInteractionLockedChange?.(true)}>
      업로드 선택 잠금
    </button>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, prefetch: vi.fn() }),
}));

vi.mock("@/shared/api/readiness", () => ({
  waitForBackendReady: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../analysis/session/api", async () => {
  const actual = await vi.importActual<
    typeof import("../analysis/session/api")
  >("../analysis/session/api");
  return {
    ...actual,
    createSamplePortfolioSession: vi.fn(),
    deletePortfolioSession: vi.fn().mockResolvedValue(undefined),
  };
});

function AnalysisProbe() {
  const { analysis } = useInsuranceData();
  return (
    <output>
      {analysis
        ? `${analysis.portfolioKind}:${analysis.insuranceDocuments.length}`
        : "empty"}
    </output>
  );
}

describe("UploadOptions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(waitForBackendReady).mockResolvedValue(undefined);
  });

  it("opens a precomputed sample as a separate analysis session", async () => {
    vi.mocked(createSamplePortfolioSession).mockResolvedValue({
      portfolioSessionToken: "sample-token",
      expiresAt: "2030-01-01T00:15:00.000Z",
      counselTurnsRemaining: 10,
      portfolioKind: "sample",
      insuranceDocuments: [
        {
          fileName: "sample.pdf",
          result: {
            ...POLICY_PARSE_RESPONSE_DEFAULTS,
            documentId: "00000000-0000-0000-0000-000000000001",
          },
        },
      ],
    });
    const user = userEvent.setup();

    renderWithProviders(
      <>
        <UploadOptions />
        <AnalysisProbe />
      </>,
    );

    await user.click(
      screen.getByRole("button", { name: "샘플 보험으로 둘러보기" }),
    );

    await waitFor(() =>
      expect(screen.getByText("sample:1")).toBeInTheDocument(),
    );
    expect(createSamplePortfolioSession).toHaveBeenCalledOnce();
    expect(routerPush).toHaveBeenCalledWith("/analysis");
  });

  it("shows progress while the sample analysis is being prepared", async () => {
    let resolveReadiness: (() => void) | undefined;
    vi.mocked(waitForBackendReady).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveReadiness = resolve;
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<UploadOptions />);

    await user.click(
      screen.getByRole("button", { name: "샘플 보험으로 둘러보기" }),
    );

    expect(
      screen.getByRole("button", { name: /서버 연결 확인 중/ }),
    ).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("분석 서버 연결 확인");

    resolveReadiness?.();

    await waitFor(() =>
      expect(createSamplePortfolioSession).toHaveBeenCalledOnce(),
    );
  });

  it("blocks the sample flow while the upload needs a user decision", async () => {
    const user = userEvent.setup();
    renderWithProviders(<UploadOptions />);

    await user.click(screen.getByRole("button", { name: "업로드 선택 잠금" }));

    expect(
      screen.getByRole("button", { name: "샘플 보험으로 둘러보기" }),
    ).toBeDisabled();
    expect(createSamplePortfolioSession).not.toHaveBeenCalled();
  });
});
