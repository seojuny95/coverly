import { useState } from "react";

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { PortfolioAnalysisPanel } from "./panel";
import type { DeathBenefitGuideInput, PortfolioSummary } from "./api";

const noop = () => {};
const deathBenefitSource = {
  label: "매일경제 · 가장의 적정 사망보험금은 연소득 3~5배",
  url: "https://www.mk.co.kr/news/economy/9495174",
  published_at: "2020-08-28",
  reliability: "private_guidance" as const,
  caveat: "민간 재무설계 관점의 일반 가이드예요.",
};
const bizwatchDiagnosisSource = {
  label: "비즈워치 · 암 진단비 평균 범위",
  url: "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
  published_at: "2024-07-06",
  reliability: "private_guidance" as const,
  caveat:
    "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요.",
};
const banksaladDiagnosisSource = {
  label: "뱅크샐러드 · 3대 진단비 구성 예시",
  url: "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EC%A2%85%ED%95%A9%EB%B3%B4%ED%97%98-%EC%A7%88%EB%B3%B4%ED%97%98",
  published_at: "2026-07-01",
  reliability: "private_guidance" as const,
  caveat: "구성 예시는 상품과 개인 상황에 따라 달라질 수 있어요.",
};
const medicalIndemnitySource = {
  label: "실손24 · 서비스 안내",
  url: "https://www.silson24.or.kr",
  published_at: "2025-01-01",
  reliability: "official" as const,
  caveat:
    "실손의료비 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요.",
};

const summary: PortfolioSummary = {
  totals: [],
  actual_loss_coverages: [],
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
        reference_min_amount: 0,
        reference_max_amount: 50_000_000,
        reference_basis:
          "사망보험금은 남은 가족의 생활비 공백을 메우는 목적이 크기 때문에, 부양가족이나 큰 부채가 없다면 큰 금액의 필요성은 낮아요. 장례비, 정리비, 부모 지원 정도만 고려하면 돼요.",
        reference_sources: [deathBenefitSource],
        reference_amount_label: "0원~5천만 원",
        guidance_situation: "부양가족이나 큰 부채가 없는 경우",
        guidance_reason:
          "사망보험금은 남은 가족의 생활비 공백을 메우는 목적이 크기 때문에, 부양가족이나 큰 부채가 없다면 큰 금액의 필요성은 낮아요. 장례비, 정리비, 부모 지원 정도만 고려하면 돼요.",
        coverage_count: 1,
        detail: "사망 담보가 확인돼요.",
        matched_coverage_names: ["질병사망"],
        coverage_groups: [
          {
            label: "기본 사망 보장",
            tone: "confirmed",
            detail:
              "일반사망·질병사망처럼 가족 생활비 목적의 사망보험 판단에 반영하는 담보예요.",
            coverage_names: ["질병사망"],
            total_amount: 100_000_000,
          },
        ],
      },
      {
        kind: "cancer",
        label: "암 진단비",
        status: "well_prepared",
        confirmed_amount: 30_000_000,
        reference_min_amount: 30_000_000,
        reference_max_amount: 50_000_000,
        reference_basis:
          "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
        reference_sources: [bizwatchDiagnosisSource, banksaladDiagnosisSource],
        coverage_count: 2,
        detail:
          "일반암·유사암·고액암·소액암을 포함해 확인된 암 진단비를 모았어요.",
        matched_coverage_names: ["암진단비", "유사암진단비"],
        coverage_groups: [
          {
            label: "암 진단비",
            tone: "confirmed",
            detail: "현재 가입금액 기준에 반영하는 일반 암 진단비예요.",
            coverage_names: ["암진단비"],
            total_amount: 30_000_000,
          },
          {
            label: "유사암 진단비",
            tone: "review",
            detail: "유사암 진단비가 가입되어 있어요.",
            coverage_names: ["유사암진단비"],
            total_amount: 5_000_000,
          },
        ],
      },
      {
        kind: "cerebrovascular",
        label: "뇌혈관질환 진단비",
        status: "not_found",
        confirmed_amount: null,
        reference_min_amount: 10_000_000,
        reference_max_amount: 20_000_000,
        reference_basis:
          "뇌혈관질환 진단비는 재활, 간병, 후유장해 가능성을 고려하는 기본 범위",
        reference_sources: [banksaladDiagnosisSource],
        coverage_count: 0,
        detail: "현재 올린 전체 보험에서는 확인하지 못했어요.",
        matched_coverage_names: [],
      },
      {
        kind: "ischemic_heart",
        label: "심장질환 진단비",
        status: "not_found",
        confirmed_amount: null,
        reference_min_amount: 10_000_000,
        reference_max_amount: 20_000_000,
        reference_basis:
          "심장질환 진단비는 시술, 수술, 입원으로 생길 수 있는 소득 공백을 고려하는 기본 범위",
        reference_sources: [banksaladDiagnosisSource],
        coverage_count: 0,
        detail: "현재 올린 증권에서는 확인하지 못했어요.",
        matched_coverage_names: [],
      },
      {
        kind: "medical_indemnity",
        label: "실손의료보험",
        status: "well_prepared",
        confirmed_amount: null,
        reference_min_amount: null,
        reference_max_amount: null,
        reference_basis:
          "실손의료보험은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인",
        reference_sources: [medicalIndemnitySource],
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
      classification_reasons: [
        "손해보험 증권 안에서 대인배상, 대물배상, 자차처럼 자동차보험 담보명이 확인돼요.",
      ],
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
    medical_indemnity: {
      name: "실손24",
      description:
        "병원이 진료비 서류를 보험사로 자동 전송해, 서류 없이 실손의료보험금을 청구하는 공식 서비스예요.",
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
    deathBenefitContext: {
      has_dependent_family: false,
      has_minor_children: false,
      has_major_debt: false,
    },
    onDeathBenefitContextChange: vi.fn(),
    eligibleCount: 1,
    emptyReason: "no-coverage" as const,
    onRetry: noop,
  };
}

function StatefulPortfolioAnalysisPanel() {
  const [deathBenefitContext, setDeathBenefitContext] =
    useState<DeathBenefitGuideInput>({
      has_dependent_family: false,
      has_minor_children: false,
      has_major_debt: false,
    });

  return (
    <PortfolioAnalysisPanel
      {...baseProps()}
      deathBenefitContext={deathBenefitContext}
      onDeathBenefitContextChange={setDeathBenefitContext}
    />
  );
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
  expect(screen.getByText("권장보험을 점검해보세요")).toBeInTheDocument();
  expect(screen.getByText("월 보험료 98,000원")).toBeInTheDocument();
  expect(screen.getByText("권장보험")).toBeInTheDocument();
  expect(screen.getByText("사망보험")).toBeInTheDocument();
  expect(screen.getByText("3대 진단보험")).toBeInTheDocument();
  expect(screen.getByText("실손의료보험")).toBeInTheDocument();
  expect(
    screen.getByRole("radio", { name: "부양가족이나 큰 부채가 없어요" }),
  ).toBeChecked();
  expect(
    screen.getByText(/피보험자가 사망했을 때 남은 가족에게/),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("부양가족이나 큰 부채가 없는 경우"),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("사망 담보가 확인돼요.")).not.toBeInTheDocument();
  expect(screen.getByText("기본 사망 보장")).toBeInTheDocument();
  expect(screen.getByText("0원~5천만 원")).toBeInTheDocument();
  expect(
    screen.queryByText("업로드한 전체 보험에서 사망 보장이 확인돼요."),
  ).not.toBeInTheDocument();
  expect(screen.getAllByText("적정 진단비 감").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/공식 출처:/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/아티클·블로그 출처:/).length).toBeGreaterThan(0);
  expect(screen.getByText(/생활비 공백/)).toBeInTheDocument();
  expect(screen.queryByText("가입이 보이는 항목")).not.toBeInTheDocument();
  expect(screen.queryByText("자료에서 찾지 못한 항목")).not.toBeInTheDocument();
  expect(screen.queryByText("함께 분석한 보험")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "사망·3대 진단비·실손의료비" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("암진단비 · 유사암진단비")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "사망 보장 안내" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("유사암 진단비")).toBeInTheDocument();
  expect(
    screen.getByText("유사암 진단비가 가입되어 있어요."),
  ).toBeInTheDocument();
  expect(screen.getByText("합계 500만원")).toBeInTheDocument();
  expect(screen.getAllByText("합계 1억").length).toBeGreaterThan(0);
  expect(
    screen.getAllByText(
      "현재 업로드된 보험증권에서는 해당 보장이 확인되지 않아요",
    ).length,
  ).toBeGreaterThan(0);
  expect(screen.getByText("손해보험 분석")).toBeInTheDocument();
  expect(screen.getByText("자동차보험")).toBeInTheDocument();
  expect(
    screen.getByText(
      "손해보험 증권 안에서 대인배상, 대물배상, 자차처럼 자동차보험 담보명이 확인돼요.",
    ),
  ).toBeInTheDocument();
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

test("allows only one death-benefit situation at a time", async () => {
  const user = userEvent.setup();
  render(<StatefulPortfolioAnalysisPanel />);

  const noDependents = screen.getByRole("radio", {
    name: "부양가족이나 큰 부채가 없어요",
  });
  const dependentFamily = screen.getByRole("radio", {
    name: "내 소득에 의존하는 가족이 있어요",
  });
  const minorChildren = screen.getByRole("radio", {
    name: "미성년 자녀가 있어요",
  });

  expect(noDependents).toBeChecked();
  expect(dependentFamily).not.toBeChecked();
  expect(minorChildren).not.toBeChecked();

  await user.click(dependentFamily);
  expect(noDependents).not.toBeChecked();
  expect(dependentFamily).toBeChecked();
  expect(minorChildren).not.toBeChecked();

  await user.click(minorChildren);
  expect(noDependents).not.toBeChecked();
  expect(dependentFamily).not.toBeChecked();
  expect(minorChildren).toBeChecked();

  await user.click(minorChildren);
  expect(minorChildren).toBeChecked();
});

test("shows a skeleton for the death benefit amount while refreshing", () => {
  render(
    <PortfolioAnalysisPanel {...baseProps()} isDeathBenefitRefreshing={true} />,
  );

  expect(screen.getByText("안내금액 계산 중")).toBeInTheDocument();
  expect(screen.queryByText("안내금액 업데이트 중...")).not.toBeInTheDocument();
});

test("groups limited death coverages separately from basic death coverage", () => {
  const limitedDeathSummary: PortfolioSummary = {
    ...summary,
    essential_coverage_check: {
      items: summary.essential_coverage_check!.items.map((item) =>
        item.kind === "death"
          ? {
              ...item,
              status: "needs_review",
              confirmed_amount: null,
              detail:
                "제한적인 사망 담보만 보여요. 가족 생활비 목적의 사망보험으로 충분한지는 따로 확인해보세요.",
              matched_coverage_names: ["대중교통이용중교통상해사망"],
              coverage_groups: [
                {
                  label: "제한적인 사망 담보",
                  tone: "limited",
                  detail:
                    "교통·대중교통·고속도로처럼 특정 사고 조건에 묶인 사망 담보예요.",
                  coverage_names: ["대중교통이용중교통상해사망"],
                },
              ],
            }
          : item,
      ),
    },
  };

  render(
    <PortfolioAnalysisPanel {...baseProps()} summary={limitedDeathSummary} />,
  );

  const deathCard = screen
    .getByRole("heading", { name: "사망보험" })
    .closest("section");

  expect(within(deathCard!).getByText("점검 필요")).toBeInTheDocument();
  expect(
    within(deathCard!).getByText("제한적인 사망 담보"),
  ).toBeInTheDocument();
  expect(
    within(deathCard!).getByText("대중교통이용중교통상해사망"),
  ).toBeInTheDocument();
  expect(
    within(deathCard!).queryByText(/확인된 담보:/),
  ).not.toBeInTheDocument();
});

test("shows the death coverage detail only when no coverage was found", () => {
  const missingDeathSummary: PortfolioSummary = {
    ...summary,
    essential_coverage_check: {
      items: (summary.essential_coverage_check?.items ?? []).map((item) =>
        item.kind === "death"
          ? {
              ...item,
              status: "not_found",
              confirmed_amount: null,
              coverage_count: 0,
              detail:
                "현재 올린 전체 보험에서는 사망 담보를 확인하지 못했어요.",
              matched_coverage_names: [],
            }
          : item,
      ),
    },
  };

  render(
    <PortfolioAnalysisPanel {...baseProps()} summary={missingDeathSummary} />,
  );

  expect(
    screen.getByText(
      "현재 올린 전체 보험에서는 사망 담보를 확인하지 못했어요.",
    ),
  ).toBeInTheDocument();
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

test("shows a multiple-medical-indemnity review directly in the coverage map", () => {
  const reviewSummary: PortfolioSummary = {
    ...summary,
    essential_coverage_check: {
      items: summary.essential_coverage_check!.items.map((item) =>
        item.kind === "medical_indemnity"
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

test("shows insurer claim channels even without the medical indemnity channel", () => {
  const insurerOnlyClaimSummary: PortfolioSummary = {
    ...summary,
    claim_channels: summary.claim_channels
      ? {
          ...summary.claim_channels,
          medical_indemnity: null,
        }
      : null,
  };

  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={insurerOnlyClaimSummary}
    />,
  );

  expect(screen.queryByText("실손24")).not.toBeInTheDocument();
  expect(screen.getByText("가입한 보험사 청구 채널 보기")).toBeInTheDocument();
  expect(
    screen.getByText(
      "가입한 보험사의 앱이나 홈페이지에서 직접 청구할 수 있어요.",
    ),
  ).toBeInTheDocument();
});

test("reviews duplicate actual-loss coverages beyond medical indemnity", () => {
  const reviewSummary: PortfolioSummary = {
    ...summary,
    actual_loss_coverages: [
      {
        policy_id: "driver-1",
        insurer: "보험사A",
        product_name: "운전자보험 A",
        coverage_name: "자동차사고벌금(실손)",
        normalized_name: "자동차사고벌금",
        original_amount: "2,000만원",
        major_category: "운전자",
        coverage_domain: "auto",
        is_medical_indemnity: false,
        is_damage_policy: true,
        duplicate_across_contracts: true,
      },
      {
        policy_id: "driver-2",
        insurer: "보험사A",
        product_name: "운전자보험 B",
        coverage_name: "자동차사고벌금(실손)",
        normalized_name: "자동차사고벌금",
        original_amount: "2,000만원",
        major_category: "운전자",
        coverage_domain: "auto",
        is_medical_indemnity: false,
        is_damage_policy: true,
        duplicate_across_contracts: true,
      },
    ],
  };

  render(<PortfolioAnalysisPanel {...baseProps()} summary={reviewSummary} />);

  const actualLossReview = screen
    .getByRole("heading", { name: "실손형 보장 중복 점검" })
    .closest("article");
  const medicalIndemnityCard = screen
    .getByRole("heading", { name: "실손의료보험" })
    .closest("section");

  expect(actualLossReview).not.toBeNull();
  expect(medicalIndemnityCard).not.toBeNull();
  expect(
    within(actualLossReview!).getByText(
      /여러 계약에서 확인된 실손형 담보: 자동차사고벌금/,
    ),
  ).toBeInTheDocument();
  expect(
    within(medicalIndemnityCard!).queryByText(/자동차사고벌금/),
  ).not.toBeInTheDocument();
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
