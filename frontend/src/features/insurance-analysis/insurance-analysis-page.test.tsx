import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { renderWithProviders } from "../../test-utils/render-with-providers";
import { InsuranceAnalysisPage } from "./insurance-analysis-page";
import type { InsuranceAnalysis } from "./insurance-analysis-store";
import { POLICY_SESSION_REFRESH_INTERVAL_MS } from "./use-policy-session-refresh";
import type { UploadInsurance } from "../insurance-upload/insurance-upload-form";

// The upload modal renders InsuranceUploadForm, which calls useRouter even
// when onAnalysisComplete is provided (it also prefetches the destination).
// Mock next/navigation so it doesn't need a real App Router context in tests.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }),
}));

const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});

// Page-level queries (summary/analysis) fire when documents exist; keep them
// deterministic with an empty summary response.
function stubEmptySummary() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          totals: [],
          actual_loss_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
        }),
      ),
    ),
  );
}

describe("InsuranceAnalysisPage", () => {
  beforeEach(() => {
    stubEmptySummary();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  test("shows insurance counts by classification", async () => {
    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              피보험자: "테스트고객",
              보험분류: "제3보험",
              상품태그: ["질병보험"],
            },
          },
        },
        {
          id: "insurance-2",
          fileName: "auto.pdf",
          result: {
            status: "accepted",
            문자수: 80,
            기본정보: {
              보험사: "현대해상화재보험",
              상품명: "개인용자동차보험",
              피보험자: "테스트고객",
              보험분류: "손해보험",
              상품태그: ["자동차보험"],
            },
          },
        },
      ],
    };

    renderWithProviders(<InsuranceAnalysisPage />, { initialAnalysis });

    expect(
      await screen.findByText("내 보험을 종류별로 정리했어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "테스트고객님의 보험을 4가지 종류로 보기 쉽게 정리했어요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "보험증권 더 올리기" }),
    ).toBeInTheDocument();

    const damageCard = screen.getAllByText("손해보험")[0].closest("div");
    const healthCard = screen.getAllByText("제3보험")[0].closest("div");

    expect(damageCard).not.toBeNull();
    expect(healthCard).not.toBeNull();
    expect(
      within(damageCard as HTMLElement).getByText("1"),
    ).toBeInTheDocument();
    expect(
      within(healthCard as HTMLElement).getByText("1"),
    ).toBeInTheDocument();
    expect(screen.getByText("자동차보험")).toBeInTheDocument();
    const lifeHelpButton = screen.getByRole("button", {
      name: "생명보험 설명 보기",
    });
    expect(lifeHelpButton).toHaveAttribute(
      "aria-controls",
      "classification-help-생명보험",
    );
    expect(lifeHelpButton).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(lifeHelpButton);

    expect(lifeHelpButton).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText(/사망이나 노후처럼 사람의 생명/),
    ).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");

    expect(lifeHelpButton).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByText(/사망이나 노후처럼 사람의 생명/),
    ).not.toBeInTheDocument();

    await userEvent.click(lifeHelpButton);
    await userEvent.click(document.body);

    expect(lifeHelpButton).toHaveAttribute("aria-expanded", "false");
  });

  test("normalizes legacy classification values into current sections", async () => {
    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "legacy-third",
          fileName: "legacy-health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "레거시 건강보험",
              보험분류: "상해·질병·실손",
              상품태그: ["실손의료보험"],
            },
          },
        },
        {
          id: "legacy-fire",
          fileName: "legacy-fire.pdf",
          result: {
            status: "accepted",
            문자수: 80,
            기본정보: {
              보험사: "현대해상",
              상품명: "레거시 화재보험",
              보험분류: "화재보험",
              상품태그: ["화재보험"],
            },
          },
        },
      ],
    };

    renderWithProviders(<InsuranceAnalysisPage />, { initialAnalysis });

    expect(await screen.findByText("레거시 건강보험")).toBeInTheDocument();
    expect(screen.getByText("레거시 화재보험")).toBeInTheDocument();

    const thirdCard = screen.getAllByText("제3보험")[0].closest("div");
    const damageCard = screen.getAllByText("손해보험")[0].closest("div");

    expect(thirdCard).not.toBeNull();
    expect(damageCard).not.toBeNull();
    expect(within(thirdCard as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(
      within(damageCard as HTMLElement).getByText("1"),
    ).toBeInTheDocument();
    expect(screen.getByText("질병·상해·간병 보장")).toBeInTheDocument();
    expect(screen.getByText("재산 손해·책임 보장")).toBeInTheDocument();
  });

  test("expands a insurance row to show detail fields", async () => {
    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              증권번호: "POLICY-TEST-001",
              계약자: "가나",
              피보험자: "가나",
              보험분류: "제3보험",
              상품태그: ["질병보험", "어린이보험"],
              납입기간: "20년납",
              만기일: "2046-01-01",
              보험기간: {
                시작일: "2026-01-01",
                종료일: "2046-01-01",
              },
              보험료: {
                금액: 120000,
                납입주기: "월납",
              },
            },
          },
        },
      ],
    };

    renderWithProviders(<InsuranceAnalysisPage />, { initialAnalysis });

    const row = await screen.findByRole("button", {
      name: /건강보험/,
    });
    expect(row).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("질병보험")).toBeInTheDocument();
    expect(screen.getByText("어린이보험")).toBeInTheDocument();

    fireEvent.click(row);

    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("POLICY-TEST-001")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 - 2046-01-01")).toBeInTheDocument();
    expect(screen.getByText("월납 120,000원")).toBeInTheDocument();
    expect(screen.queryByText("상품명")).not.toBeInTheDocument();
    expect(screen.queryByText("상품태그")).not.toBeInTheDocument();
  });

  test("renders every display field and insurer logo when an insurance document has full data", async () => {
    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객A",
      insuranceDocuments: [
        {
          id: "insurance-full",
          fileName: "db-driver.pdf",
          result: {
            status: "accepted",
            문자수: 200,
            기본정보: {
              보험사: "삼성화재해상보험주식회사",
              상품명: "마이헬스파트너",
              증권번호: "POLICY-TEST-002",
              계약자: "테스트고객A",
              피보험자: "테스트고객A",
              보험분류: "제3보험",
              상품태그: ["질병보험", "어린이보험"],
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
          },
        },
      ],
    };

    const { container } = renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis,
    });

    const row = await screen.findByRole("button", {
      name: /마이헬스파트너/,
    });

    expect(screen.getByText("db-driver.pdf")).toBeInTheDocument();
    expect(screen.getByText("질병보험")).toBeInTheDocument();
    expect(screen.getByText("어린이보험")).toBeInTheDocument();

    const logo = container.querySelector('img[src*="samsung-fire.png"]');
    expect(logo).not.toBeNull();

    fireEvent.click(row);

    const detail = row.closest("div");
    expect(detail).not.toBeNull();
    expect(screen.getByText("보험사")).toBeInTheDocument();
    expect(screen.getByText("삼성화재해상보험주식회사")).toBeInTheDocument();
    expect(screen.getByText("증권번호")).toBeInTheDocument();
    expect(screen.getByText("POLICY-TEST-002")).toBeInTheDocument();
    expect(screen.getByText("계약자")).toBeInTheDocument();
    expect(screen.getAllByText("테스트고객A").length).toBeGreaterThan(1);
    expect(screen.getByText("피보험자")).toBeInTheDocument();
    expect(screen.getByText("보험기간")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 - 2027-01-01")).toBeInTheDocument();
    expect(screen.getByText("만기일")).toBeInTheDocument();
    expect(screen.getByText("2027-01-01")).toBeInTheDocument();
    expect(screen.getByText("납입기간")).toBeInTheDocument();
    expect(screen.getByText("20년납")).toBeInTheDocument();
    expect(screen.getByText("보험료")).toBeInTheDocument();
    expect(screen.getByText("월납 120,000원")).toBeInTheDocument();
  });

  test("shows vehicle info and separates rider rows for an auto policy", async () => {
    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "auto-insurance",
          fileName: "auto.pdf",
          result: {
            status: "accepted",
            문자수: 150,
            기본정보: {
              보험사: "현대해상화재보험",
              상품명: "개인용자동차보험",
              피보험자: "테스트고객",
              보험분류: "손해보험",
              상품태그: ["자동차보험"],
              차량정보: {
                차량명: "아반떼",
                차량번호: "TEST-PLATE-001",
                연식: "2024",
              },
            },
            보장목록: [
              {
                담보명: "대인배상Ⅰ",
                가입금액: "무한",
                보장내용: "법률상 손해배상책임을 짐으로써 입은 손해를 보상",
                해설: null,
              },
              {
                담보명: "마일리지 특약",
                가입금액: "",
                보장내용: null,
                해설: null,
                유형: "부가",
              },
            ],
          },
        },
      ],
    };

    renderWithProviders(<InsuranceAnalysisPage />, { initialAnalysis });

    const row = await screen.findByRole("button", {
      name: /개인용자동차보험/,
    });
    fireEvent.click(row);

    expect(screen.getByText("차량명")).toBeInTheDocument();
    expect(screen.getByText("아반떼")).toBeInTheDocument();
    expect(screen.getByText("차량번호")).toBeInTheDocument();
    expect(screen.getByText("TEST-PLATE-001")).toBeInTheDocument();
    expect(screen.getByText("연식")).toBeInTheDocument();
    expect(screen.getByText("2024")).toBeInTheDocument();

    expect(screen.getByText("대인배상Ⅰ")).toBeInTheDocument();
    expect(screen.getByText("부가 특약·요율")).toBeInTheDocument();
    expect(screen.getByText("마일리지 특약")).toBeInTheDocument();
  });

  test("renders DB insurer name and logo for a parsed driver insurance document", async () => {
    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객A",
      insuranceDocuments: [
        {
          id: "db-driver-insurance",
          fileName: "DB운전자보험증권.pdf",
          result: {
            status: "accepted",
            문자수: 200,
            기본정보: {
              보험사: "DB손해보험",
              상품명: "무배당 프로미라이프 참좋은운전자상해보험(TM)2404",
              증권번호: "POLICY-TEST-MASKED-001",
              계약자: "테스트고객A",
              피보험자: "테스트고객A",
              보험분류: "손해보험",
              상품태그: ["운전자보험"],
              납입기간: "20년납",
              만기일: "2044-07-26",
              보험기간: {
                시작일: "2024-07-26",
                종료일: "2044-07-26",
              },
              보험료: {
                금액: 11670,
                납입주기: "월납",
              },
            },
          },
        },
      ],
    };

    const { container } = renderWithProviders(<InsuranceAnalysisPage />, {
      initialAnalysis,
    });
    const row = await screen.findByRole("button", {
      name: /무배당 프로미라이프 참좋은운전자상해보험/,
    });

    expect(
      container.querySelector('img[src*="db-insurance.png"]'),
    ).not.toBeNull();

    fireEvent.click(row);

    expect(screen.getByText("보험사")).toBeInTheDocument();
    expect(screen.getByText("DB손해보험")).toBeInTheDocument();
    expect(screen.getByText("증권번호")).toBeInTheDocument();
    expect(screen.getByText("POLICY-TEST-MASKED-001")).toBeInTheDocument();
    expect(screen.getByText("보험기간")).toBeInTheDocument();
    expect(screen.getByText("2024-07-26 - 2044-07-26")).toBeInTheDocument();
    expect(screen.getByText("보험료")).toBeInTheDocument();
    expect(screen.getByText("월납 11,670원")).toBeInTheDocument();
  });

  test("shows an empty state when no analysis exists", async () => {
    renderWithProviders(<InsuranceAnalysisPage />);

    expect(
      await screen.findByText("분석할 보험증권이 없어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "보험증권 올리기" }),
    ).toHaveAttribute("href", "/upload");
  });

  test("refreshes document session tokens while the analysis page is open", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/policies/sessions/refresh")) {
        return new Response(
          JSON.stringify({
            문서세션ID: "new-session-token",
            expiresAt: "2026-07-14T00:15:00+00:00",
          }),
        );
      }
      return new Response(
        JSON.stringify({
          totals: [],
          actual_loss_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            문서세션ID: "old-session-token",
          },
        },
      ],
    };

    renderWithProviders(<InsuranceAnalysisPage />, { initialAnalysis });

    act(() => {
      vi.advanceTimersByTime(POLICY_SESSION_REFRESH_INTERVAL_MS);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/policies/sessions/refresh",
      expect.objectContaining({
        body: JSON.stringify({ 문서세션ID: "old-session-token" }),
      }),
    );
  });

  test("shows a session expiration notice when refresh is rejected", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/policies/sessions/refresh")) {
        return new Response(
          JSON.stringify({ error: { code: "INVALID_POLICY_SESSION" } }),
          { status: 403 },
        );
      }
      return new Response(
        JSON.stringify({
          totals: [],
          actual_loss_coverages: [],
          excluded_coverages: [],
          excluded_auto_policy_count: 0,
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            문서세션ID: "expired-session-token",
          },
        },
      ],
    };

    renderWithProviders(<InsuranceAnalysisPage />, { initialAnalysis });

    act(() => {
      vi.advanceTimersByTime(POLICY_SESSION_REFRESH_INTERVAL_MS);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("분석 세션이 만료됐어요")).toBeInTheDocument();
    expect(
      screen.getByText(
        "개인정보 보호를 위해 업로드한 문서 연결이 종료되었어요. 다시 분석하려면 보험증권을 다시 올려주세요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "보험증권 다시 올리기" }),
    ).toHaveAttribute("href", "/upload");
  });

  test("opens an upload modal and merges uploaded insuranceDocuments into the current analysis", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      status: "accepted",
      문자수: 80,
      기본정보: {
        보험사: "현대해상화재보험",
        상품명: "개인용자동차보험",
        피보험자: "테스트고객",
        보험분류: "손해보험",
        상품태그: ["자동차보험"],
      },
    });

    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              피보험자: "테스트고객",
              보험분류: "제3보험",
              상품태그: ["질병보험"],
            },
          },
        },
      ],
    };

    renderWithProviders(
      <InsuranceAnalysisPage uploadInsurance={uploadInsurance} />,
      { initialAnalysis },
    );

    await user.click(
      await screen.findByRole("button", { name: "보험증권 더 올리기" }),
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "보험증권 더 올리기" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("테스트고객(피보험자)의 보험증권 PDF만 올릴 수 있어요"),
    ).toBeInTheDocument();
    expect(screen.queryByText("보험증권 PDF")).not.toBeInTheDocument();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "분석에 추가하기" }));

    expect(uploadInsurance).toHaveBeenCalledWith(
      { file: insuranceFile },
      expect.anything(),
    );
    expect(
      await screen.findByText(
        "테스트고객님의 보험을 4가지 종류로 보기 쉽게 정리했어요.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("자동차보험")).toBeInTheDocument();
  });

  test("keeps duplicate policy uploads out of the current analysis", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      status: "accepted",
      문자수: 80,
      기본정보: {
        보험사: "삼성화재",
        상품명: "건강보험",
        증권번호: "POLICY-TEST-001",
        피보험자: "테스트고객",
        보험분류: "제3보험",
        상품태그: ["질병보험"],
      },
    });

    const initialAnalysis: InsuranceAnalysis = {
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              증권번호: "POLICY-TEST-001",
              피보험자: "테스트고객",
              보험분류: "제3보험",
              상품태그: ["질병보험"],
            },
          },
        },
      ],
    };

    renderWithProviders(
      <InsuranceAnalysisPage uploadInsurance={uploadInsurance} />,
      { initialAnalysis },
    );

    await user.click(
      await screen.findByRole("button", { name: "보험증권 더 올리기" }),
    );
    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "분석에 추가하기" }));

    expect(
      await screen.findByText(
        "이미 올린 보험증권이에요. insurance.pdf 파일을 제거하고 다시 시도해주세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByText(
        "테스트고객님의 보험을 4가지 종류로 보기 쉽게 정리했어요.",
      ),
    ).toBeInTheDocument();
  });
});
