import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { PortfolioAnalysisPanel } from "./portfolio-analysis-panel";
import type { PortfolioSummary } from "./portfolio-api";

const noop = () => {};

const summary: PortfolioSummary = {
  totals: [],
  indemnity_coverages: [],
  excluded_coverages: [],
  excluded_auto_policy_count: 0,
  overview: {
    generation: "llm",
    title: "보험료는 낮지만, 진단비 공백을 먼저 확인해야 해요",
    paragraphs: ["현재 보장 구성을 바탕으로 확인한 내용을 정리했어요."],
    takeaways: [
      {
        label: "우선 확인",
        title: "진단비 공백",
        detail: "뇌혈관질환과 심장질환 진단비를 확인해보세요.",
      },
    ],
  },
  essential_coverage_check: {
    items: [
      {
        kind: "death",
        label: "사망 보장",
        status: "well_prepared",
        confirmed_amount: 100_000_000,
        reference_min_amount: 10_000_000,
        reference_max_amount: 20_000_000,
        coverage_count: 1,
        detail: "업로드한 전체 보험에서 사망 보장이 확인돼요.",
        matched_coverage_names: ["질병사망"],
      },
      {
        kind: "cancer",
        label: "암 진단비",
        status: "well_prepared",
        confirmed_amount: 35_000_000,
        reference_min_amount: 30_000_000,
        reference_max_amount: 50_000_000,
        coverage_count: 2,
        detail:
          "일반암·유사암·고액암·소액암을 포함해 확인된 암 진단비를 모았어요.",
        matched_coverage_names: ["암진단비", "유사암진단비"],
      },
      {
        kind: "cerebrovascular",
        label: "뇌혈관질환 진단비",
        status: "not_found",
        confirmed_amount: null,
        reference_min_amount: 30_000_000,
        reference_max_amount: 30_000_000,
        coverage_count: 0,
        detail: "현재 올린 전체 보험에서는 확인하지 못했어요.",
        matched_coverage_names: [],
      },
      {
        kind: "ischemic_heart",
        label: "심장질환 진단비",
        status: "not_found",
        confirmed_amount: null,
        reference_min_amount: 20_000_000,
        reference_max_amount: 30_000_000,
        coverage_count: 0,
        detail: "현재 올린 증권에서는 확인하지 못했어요.",
        matched_coverage_names: [],
      },
      {
        kind: "indemnity",
        label: "실손의료보험",
        status: "well_prepared",
        confirmed_amount: null,
        reference_min_amount: null,
        reference_max_amount: null,
        coverage_count: 2,
        detail: "실손의료보험 가입 사실이 확인돼요.",
        matched_coverage_names: ["질병실손의료비", "상해실손의료비"],
      },
    ],
  },
  special_policy_analyses: [
    {
      kind: "auto",
      label: "자동차보험",
      policy_count: 1,
      product_names: ["개인용 자동차보험"],
      confirmed_coverage_names: ["대인배상Ⅰ", "대물배상"],
      overview:
        "상대방의 신체 피해와 상대방의 재물 피해는 확인돼요. 나머지는 현재 자료에서 더 확인해야 해요.",
      coverage_checks: [
        {
          label: "상대방의 신체 피해",
          status: "confirmed",
          detail: "사고로 다른 사람이 다치거나 사망했을 때의 배상 담보예요.",
          matched_coverage_names: ["대인배상Ⅰ"],
        },
        {
          label: "내 차량 손해",
          status: "not_found",
          detail: "가입 차량에 생긴 손해를 위한 담보예요.",
          matched_coverage_names: [],
        },
      ],
    },
    {
      kind: "driver",
      label: "운전자보험",
      policy_count: 1,
      product_names: ["안심 운전자보험"],
      confirmed_coverage_names: ["교통사고처리지원금"],
      overview: "교통사고 처리 지원은 확인돼요.",
      coverage_checks: [
        {
          label: "교통사고 처리 지원",
          status: "confirmed",
          detail: "형사합의가 필요한 교통사고의 비용 부담을 위한 담보예요.",
          matched_coverage_names: ["교통사고처리지원금"],
        },
      ],
    },
    {
      kind: "travel",
      label: "여행자보험",
      policy_count: 1,
      product_names: ["해외여행보험"],
      confirmed_coverage_names: ["해외의료비"],
      overview: "해외 의료비는 확인돼요.",
      coverage_checks: [
        {
          label: "해외 의료비",
          status: "confirmed",
          detail:
            "여행 중 질병이나 상해로 해외에서 지출한 의료비를 위한 담보예요.",
          matched_coverage_names: ["해외의료비"],
        },
      ],
    },
    {
      kind: "fire",
      label: "화재보험",
      policy_count: 1,
      product_names: ["우리집 화재보험"],
      confirmed_coverage_names: ["화재손해"],
      overview: "건물·가재 화재 손해는 확인돼요.",
      coverage_checks: [
        {
          label: "건물·가재 화재 손해",
          status: "confirmed",
          detail: "화재로 건물이나 가재도구에 생긴 직접 손해를 위한 담보예요.",
          matched_coverage_names: ["화재손해"],
        },
      ],
    },
  ],
  claim_channels: {
    insurers: [
      {
        name: "삼성화재",
        customer_center: "1588-5114",
        note: "홈페이지에서 보험금 청구 메뉴를 확인할 수 있어요.",
        links: [
          { label: "청구 링크", url: "https://www.samsungfire.com" },
          { label: "홈페이지", url: "https://www.samsungfire.com" },
        ],
      },
      {
        name: "메리츠화재",
        customer_center: "1566-7711",
        note: "홈페이지 > 보험금청구에서 접수할 수 있어요.",
        links: [{ label: "청구 링크", url: "https://www.meritzfire.com" }],
      },
    ],
    indemnity: {
      name: "실손24",
      description:
        "병원이 진료비 서류를 보험사로 자동 전송해, 서류 없이 실손보험금을 청구하는 공식 서비스예요.",
      call_center: "1811-3000",
      links: [
        {
          label: "실손24 홈페이지",
          url: "https://www.silson24.or.kr/claim/web/",
        },
      ],
    },
  },
  premium: {
    monthly_total: 98_000,
    monthly_policy_count: 3,
    unconfirmed_policy_count: 0,
    items: [
      {
        policy_id: "p1",
        insurer: "삼성화재",
        product_name: "건강보험",
        monthly_amount: 42_000,
        cycle: "월납",
      },
    ],
  },
  premium_benchmark: {
    age_band_label: "20~30대",
    min_age: 20,
    max_age: 39,
    average_monthly_income: 3_860_000,
    suggested_min_ratio: 0.05,
    suggested_max_ratio: 0.1,
    suggested_min_premium: 193_000,
    suggested_max_premium: 386_000,
    income_source: {
      label: "KOSIS 국가통계포털 · 성별 연령대별 소득",
      url: "https://kosis.kr",
      published_at: "2025-01-01",
      reliability: "official",
      caveat: "연령대 평균 소득은 개인 소득과 다를 수 있어요.",
    },
    guide_source: {
      label: "뱅크샐러드 · 나에게 맞는 보험료 계산법",
      url: "https://www.banksalad.com/articles/",
      published_at: "2025-01-01",
      reliability: "private_guidance",
      caveat:
        "월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.",
    },
  },
};

function baseProps() {
  return {
    status: "success" as const,
    summary,
    eligibleCount: 1,
    emptyReason: "no-coverage" as const,
    onRetry: noop,
  };
}

test("shows an empty state only when there are no insurance documents", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      eligibleCount={0}
      emptyReason="auto-only"
    />,
  );

  expect(screen.getByText("확인할 보험 정보가 없어요")).toBeInTheDocument();
});

test("shows all-policy core, special-policy, and claim checks", async () => {
  const user = userEvent.setup();
  render(<PortfolioAnalysisPanel {...baseProps()} />);

  expect(screen.getByText("전체 보험 총평")).toBeInTheDocument();
  expect(screen.queryByText("가입 확인 현황")).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", {
      name: "보험료는 낮지만, 진단비 공백을 먼저 확인해야 해요",
    }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("현재 보장 구성을 바탕으로 확인한 내용을 정리했어요."),
  ).toBeInTheDocument();
  expect(screen.getByText("진단비 공백")).toBeInTheDocument();
  expect(
    screen.getByText("보험료는 낮지만 권장보험 점검이 필요해요"),
  ).toBeInTheDocument();
  expect(screen.getByText("월 보험료 98,000원")).toBeInTheDocument();
  expect(screen.getByText("권장보험")).toBeInTheDocument();
  expect(screen.getByText("사망보험")).toBeInTheDocument();
  expect(screen.getByText("3대 진단보험")).toBeInTheDocument();
  expect(screen.getByText("실손의료보험")).toBeInTheDocument();
  expect(screen.getByText("기본 장례비 기준")).toBeInTheDocument();
  expect(screen.getAllByText("민간 가이드 기준").length).toBeGreaterThan(0);
  expect(screen.queryByText("가입이 보이는 항목")).not.toBeInTheDocument();
  expect(screen.queryByText("자료에서 찾지 못한 항목")).not.toBeInTheDocument();
  expect(screen.queryByText("함께 분석한 보험")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "사망·3대 진단비·실손" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("암진단비 · 유사암진단비")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "사망 보장 안내" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("손해보험 분석")).toBeInTheDocument();
  expect(screen.getByText("자동차보험")).toBeInTheDocument();
  expect(screen.getByText("운전자보험")).toBeInTheDocument();
  expect(screen.getByText("여행자보험")).toBeInTheDocument();
  expect(screen.getByText("화재보험")).toBeInTheDocument();
  expect(screen.getByText("보험금 청구 방법")).toBeInTheDocument();
  expect(screen.getByText("접수까지 네 단계로 준비해요")).toBeInTheDocument();
  expect(screen.queryByText("최근 제도 변화")).not.toBeInTheDocument();
  expect(screen.getByText("상대방의 신체 피해")).toBeInTheDocument();
  expect(screen.getByText("내 차량 손해")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "실손24 홈페이지" })).toHaveAttribute(
    "href",
    "https://www.silson24.or.kr/claim/web/",
  );
  const insurerChannels = screen
    .getByText("가입한 보험사 청구 채널 보기")
    .closest("details");
  expect(insurerChannels).not.toHaveAttribute("open");
  await user.click(screen.getByText("가입한 보험사 청구 채널 보기"));
  expect(insurerChannels).toHaveAttribute("open");
  expect(screen.getByText("삼성화재")).toBeInTheDocument();
  expect(screen.getByText("메리츠화재")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "청구 링크" })[0]).toHaveAttribute(
    "href",
    "https://www.samsungfire.com",
  );
  expect(screen.queryByText("확인된 보장")).not.toBeInTheDocument();
  expect(screen.queryByText("추가 확인")).not.toBeInTheDocument();
});

test("shows an explicit retry state when the LLM overview is missing", async () => {
  const onRetry = vi.fn();
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={{ ...summary, overview: null }}
      onRetry={onRetry}
    />,
  );

  expect(screen.getByText("총평을 생성하지 못했어요")).toBeInTheDocument();
  expect(
    screen.queryByText("보험료는 낮지만, 진단비 공백을 먼저 확인해야 해요"),
  ).not.toBeInTheDocument();

  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "총평 다시 생성하기" }));
  expect(onRetry).toHaveBeenCalledOnce();
});

test("shows a multiple-indemnity review directly in the coverage map", () => {
  const reviewSummary: PortfolioSummary = {
    ...summary,
    essential_coverage_check: {
      items: summary.essential_coverage_check!.items.map((item) =>
        item.kind === "indemnity"
          ? {
              ...item,
              status: "needs_review",
              detail:
                "실손의료보험이 여러 계약에서 확인돼요. 중복 가입 여부를 확인해보세요.",
            }
          : item,
      ),
    },
  };

  render(<PortfolioAnalysisPanel {...baseProps()} summary={reviewSummary} />);

  expect(screen.queryByText("한 번 더 볼 항목")).not.toBeInTheDocument();
  expect(screen.getByText("중복 가능성 확인")).toBeInTheDocument();
});

test("shows the loading state while the deterministic summary runs", () => {
  render(<PortfolioAnalysisPanel {...baseProps()} status="loading" />);

  expect(
    screen.getByText("전체 보험의 핵심 보장을 확인하고 있어요"),
  ).toBeInTheDocument();
});

test("calls onRetry from the error state", async () => {
  const onRetry = vi.fn();
  const { default: userEvent } = await import("@testing-library/user-event");
  const user = userEvent.setup();
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      status="error"
      onRetry={onRetry}
    />,
  );

  await user.click(screen.getByRole("button", { name: "다시 확인하기" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});
