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
    title: "진단비 구성에서 더 확인할 부분이 있어요",
    paragraphs: ["현재 보장 구성을 바탕으로 확인한 내용을 정리했어요."],
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
    policyCount: 1,
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

test("shows all-policy core, special-policy, and claim checks", async () => {
  const user = userEvent.setup();
  render(<PortfolioAnalysisPanel {...baseProps()} />);

  expect(screen.getByText("전체 보험 총평")).toBeInTheDocument();
  expect(screen.queryByText("가입 확인 현황")).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", {
      name: "진단비 구성에서 더 확인할 부분이 있어요",
    }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("현재 보장 구성을 바탕으로 확인한 내용을 정리했어요."),
  ).toBeInTheDocument();
  expect(screen.getByText("현재 월 보험료")).toBeInTheDocument();
  expect(screen.getByText("20~30대 권장금액")).toBeInTheDocument();
  expect(screen.getByText("월 보험료 98,000원")).toBeInTheDocument();
  expect(
    screen.getByRole("group", {
      name: "현재 98,000원, 권장 193,000원 ~ 386,000원",
    }),
  ).toBeInTheDocument();
  expect(screen.getByText("핵심 보장 확인")).toBeInTheDocument();
  expect(screen.getByText("실손형 보장 중복 확인")).toBeInTheDocument();
  expect(screen.getAllByText("사망 보장").length).toBeGreaterThan(0);
  expect(screen.getByText("진단 보장")).toBeInTheDocument();
  expect(screen.getByText("실손의료보험")).toBeInTheDocument();
  expect(screen.queryByText("진단 이후 생활")).not.toBeInTheDocument();
  expect(screen.queryByText("실제 의료비")).not.toBeInTheDocument();
  expect(
    screen.getByText(
      "사망 보장은 피보험자가 사망했을 때 남은 가족의 생활비, 부채 상환처럼 생길 수 있는 경제적 공백을 대비하는 보장이에요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "진단 보장은 큰 질병을 진단받은 뒤 치료와 회복 기간에 생길 수 있는 생활비 공백을 대비하는 보장이에요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "암 진단 시 약정된 금액을 지급하는 정액 보장으로, 치료와 회복 중 생활비 공백을 대비해요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "뇌혈관질환 진단 시 약정된 금액을 지급하는 정액 보장으로, 재활과 간병에 드는 비용을 대비해요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "심장질환 진단 시 약정된 금액을 지급하는 정액 보장으로, 시술·수술과 회복 기간의 비용을 대비해요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "실손의료보험은 실제로 부담한 의료비를 약관의 보장 범위 안에서 보상하는 보험이에요. 의료비 부담을 줄이는 보장이라 가입 세대, 자기부담금, 중복 여부를 함께 확인해야 해요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("radio", { name: "부양가족이나 큰 부채가 없어요" }),
  ).toBeChecked();
  expect(
    screen.queryByText("부양가족이나 큰 부채가 없는 경우"),
  ).not.toBeInTheDocument();
  expect(screen.getByText("부양가족이나 큰 부채가 없어요")).toHaveClass(
    "font-semibold",
    "text-blue-700",
  );
  expect(screen.queryByText("사망 담보가 확인돼요.")).not.toBeInTheDocument();
  expect(screen.getByText("기본 사망 보장")).toBeInTheDocument();
  expect(screen.getByText("0원~5천만 원")).toBeInTheDocument();
  expect(
    screen.queryByText("업로드한 전체 보험에서 사망 보장이 확인돼요."),
  ).not.toBeInTheDocument();
  expect(screen.getAllByText("권장금액").length).toBeGreaterThan(0);
  expect(screen.queryByText("확인 기준")).not.toBeInTheDocument();
  expect(screen.queryByText("참고 금액")).not.toBeInTheDocument();
  const compactRecommendedAmount = screen
    .getAllByText("3,000만원 ~ 5,000만원")
    .find((element) => element.tagName === "P");
  expect(compactRecommendedAmount).toHaveClass("whitespace-nowrap");
  expect(
    screen.getAllByRole("group", {
      name: "현재 3,000만원, 권장 3,000만원 ~ 5,000만원",
    }).length,
  ).toBeGreaterThan(0);
  expect(screen.getAllByText(/공식 출처:/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/아티클·블로그 출처:/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/생활비 공백/).length).toBeGreaterThan(0);
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
  expect(
    screen.getByText("청구 순서와 접수 채널을 확인해요"),
  ).toBeInTheDocument();
  expect(screen.getByText("보장 내용 확인")).toBeInTheDocument();
  expect(screen.getByText("필요 서류 준비")).toBeInTheDocument();
  expect(screen.getByText("청구 접수")).toBeInTheDocument();
  expect(screen.getByText("진행 상황 확인")).toBeInTheDocument();
  expect(screen.queryByText(/청구권은 일반적으로/)).not.toBeInTheDocument();
  expect(
    screen.queryByText(/공통으로 청구서와 신분증/),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/가입 당시 알린 내용/)).not.toBeInTheDocument();
  expect(
    screen.getByText(/본인확인 → 보험사 선택 → 진료·처방 내역 선택/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/실손24와 연계된 병원·약국인지 먼저 확인/),
  ).toBeInTheDocument();
  expect(screen.queryByText("최근 제도 변화")).not.toBeInTheDocument();
  expect(screen.getByText("상대방의 신체 피해")).toBeInTheDocument();
  expect(screen.getByText("내 차량 손해")).toBeInTheDocument();
  const claimSubmissionStep = screen.getByText("청구 접수").closest("li");
  expect(claimSubmissionStep).not.toBeNull();
  expect(
    within(claimSubmissionStep!).getByRole("link", {
      name: "실손24 홈페이지",
    }),
  ).toHaveAttribute("href", "https://www.silson24.or.kr/claim/web/");
  const insurerChannelsTrigger = screen.getByRole("button", {
    name: /가입한 보험사별 청구 채널/,
  });
  expect(insurerChannelsTrigger).toHaveAttribute("aria-expanded", "false");

  // jsdom's accessibility-tree queries don't honor `inert`, so a collapsed
  // link is still findable by role here; assert the `inert` ancestor
  // directly to prove it is actually removed from the tab order.
  const collapsedClaimLinks = screen.getAllByRole("link", {
    name: "청구 링크",
  });
  for (const link of collapsedClaimLinks) {
    expect(link.closest("[inert]")).not.toBeNull();
  }

  await user.click(insurerChannelsTrigger);
  expect(insurerChannelsTrigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("삼성화재")).toBeInTheDocument();
  expect(screen.getByText("메리츠화재")).toBeInTheDocument();
  const expandedClaimLinks = screen.getAllByRole("link", {
    name: "청구 링크",
  });
  for (const link of expandedClaimLinks) {
    expect(link.closest("[inert]")).toBeNull();
  }
  expect(expandedClaimLinks[0]).toHaveAttribute(
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

  expect(
    screen.getByRole("status", { name: "권장금액을 다시 확인하고 있어요" }),
  ).toHaveAttribute("aria-busy", "true");
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
    .getByRole("heading", { name: "사망 보장" })
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

test("shows overview copy generation separately from confirmed analysis data", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={{ ...summary, overview: null }}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent(
    "총평을 정리하고 있어요",
  );
  expect(
    screen.getByText(
      "확인된 보장과 보험료 정보는 먼저 볼 수 있어요. 총평 문장만 이어서 준비하고 있어요.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "총평 다시 생성하기" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("group", {
      name: "현재 98,000원, 권장 193,000원 ~ 386,000원",
    }),
  ).toBeInTheDocument();
});

test("animates the generated overview copy into the existing card", () => {
  render(<PortfolioAnalysisPanel {...baseProps()} />);

  expect(
    screen.getByRole("heading", {
      name: "진단비 구성에서 더 확인할 부분이 있어요",
    }).parentElement,
  ).toHaveClass("animate-enter");
});

test("shows an explicit retry state when overview generation fails", async () => {
  const onRetry = vi.fn();
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={{ ...summary, overview: null }}
      onRetry={onRetry}
      overviewRetryFailed
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

test("keeps the premium comparison visible while regenerating a missing overview", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={{ ...summary, overview: null }}
      isOverviewRetrying
    />,
  );

  expect(screen.getByText("총평을 정리하고 있어요")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "총평 다시 생성하는 중…" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("group", {
      name: "현재 98,000원, 권장 193,000원 ~ 386,000원",
    }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("progressbar", { name: "총평 다시 생성 진행" }),
  ).not.toBeInTheDocument();
});

test("keeps the current monthly premium visible without an age benchmark", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={{ ...summary, premium_benchmark: null }}
    />,
  );

  expect(screen.getAllByText("현재 월 보험료").length).toBeGreaterThan(0);
  expect(screen.getByText("연령 정보 확인 필요")).toBeInTheDocument();
  expect(
    screen.getByText(
      "보험증권에서 나이를 확인하지 못해 권장금액은 계산하지 않았어요.",
    ),
  ).toBeInTheDocument();
});

test("explains when regenerating the overview fails again", () => {
  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={{ ...summary, overview: null }}
      overviewRetryFailed
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "총평 문장만 생성하지 못했어요. 확인된 보장과 보험료 정보는 그대로",
  );
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
  expect(screen.getByText("추가 확인")).toBeInTheDocument();
});

test("shows the Silson24 link without treating medical indemnity as held", () => {
  const insurerOnlyClaimSummary: PortfolioSummary = {
    ...summary,
    essential_coverage_check: {
      items: summary.essential_coverage_check!.items.map((item) =>
        item.kind === "medical_indemnity"
          ? { ...item, status: "not_found" }
          : item,
      ),
    },
  };

  render(
    <PortfolioAnalysisPanel
      {...baseProps()}
      summary={insurerOnlyClaimSummary}
    />,
  );

  expect(
    screen.getByRole("link", { name: "실손24 홈페이지" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/실손의료보험은 실손24로 청구할 수 있어요/),
  ).not.toBeInTheDocument();
  expect(screen.getByText("가입한 보험사별 청구 채널")).toBeInTheDocument();
  expect(
    screen.getByText("가입한 보험사의 접수 링크와 고객센터만 모았어요."),
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
    .getByRole("heading", { name: "실손의료보험 외에 겹쳐 있는 보장" })
    .closest("article");
  const medicalIndemnityCard = screen
    .getByRole("heading", { name: "실손의료보험" })
    .closest("section");

  expect(actualLossReview).not.toBeNull();
  expect(medicalIndemnityCard).not.toBeNull();
  expect(
    within(actualLossReview!).getByText("실손형 보장 중복 확인"),
  ).toBeInTheDocument();
  expect(
    within(actualLossReview!).getByText("중복 확인된 비의료 실손형 담보 1건"),
  ).toBeInTheDocument();
  expect(
    within(actualLossReview!).getByText("자동차사고벌금(실손)"),
  ).toBeInTheDocument();
  expect(
    within(actualLossReview!).getByText(
      "정액 진단비가 아니라 실제 발생한 벌금 손해를 약관 한도 안에서 보상하는 실손형 담보예요.",
    ),
  ).toBeInTheDocument();
  expect(
    within(actualLossReview!).getByText(
      "보험사A · 운전자보험 A · 자동차사고벌금(실손)",
    ),
  ).toBeInTheDocument();
  expect(
    within(actualLossReview!).getByText(
      "보험사A · 운전자보험 B · 자동차사고벌금(실손)",
    ),
  ).toBeInTheDocument();
  expect(
    within(medicalIndemnityCard!).queryByText(/자동차사고벌금/),
  ).not.toBeInTheDocument();
});

test("reviews duplicate medical indemnity coverages inside the medical card", async () => {
  const user = userEvent.setup();
  const reviewSummary: PortfolioSummary = {
    ...summary,
    actual_loss_coverages: [
      {
        policy_id: "medical-1",
        insurer: "보험사A",
        product_name: "실손보험 A",
        coverage_name: "상해실손의료비",
        normalized_name: "상해실손의료비",
        original_amount: "5,000만원",
        major_category: "치료",
        coverage_domain: "medical_expense",
        is_medical_indemnity: true,
        is_damage_policy: false,
        duplicate_across_contracts: true,
      },
      {
        policy_id: "medical-2",
        insurer: "보험사B",
        product_name: "실손보험 B",
        coverage_name: "상해실손의료비",
        normalized_name: "상해실손의료비",
        original_amount: "5,000만원",
        major_category: "치료",
        coverage_domain: "medical_expense",
        is_medical_indemnity: true,
        is_damage_policy: false,
        duplicate_across_contracts: true,
      },
      {
        policy_id: "medical-1",
        insurer: "보험사A",
        product_name: "실손보험 A",
        coverage_name: "질병실손의료비",
        normalized_name: "질병실손의료비",
        original_amount: "5,000만원",
        major_category: "치료",
        coverage_domain: "medical_expense",
        is_medical_indemnity: true,
        is_damage_policy: false,
        duplicate_across_contracts: true,
      },
      {
        policy_id: "medical-2",
        insurer: "보험사B",
        product_name: "실손보험 B",
        coverage_name: "질병실손의료비",
        normalized_name: "질병실손의료비",
        original_amount: "5,000만원",
        major_category: "치료",
        coverage_domain: "medical_expense",
        is_medical_indemnity: true,
        is_damage_policy: false,
        duplicate_across_contracts: true,
      },
    ],
  };

  render(<PortfolioAnalysisPanel {...baseProps()} summary={reviewSummary} />);

  const medicalIndemnityCard = screen
    .getByRole("heading", { name: "실손의료보험" })
    .closest("section");
  const actualLossReview = screen
    .getByRole("heading", { name: "실손의료보험 외에 겹쳐 있는 보장" })
    .closest("article");

  expect(medicalIndemnityCard).not.toBeNull();
  expect(actualLossReview).not.toBeNull();
  expect(
    within(medicalIndemnityCard!).getByText(
      "중복된 실손의료비 2종 · 담보 내역 4건",
    ),
  ).toBeInTheDocument();
  expect(
    within(medicalIndemnityCard!).queryByText("실손의료보험 중복 확인"),
  ).not.toBeInTheDocument();
  expect(
    within(medicalIndemnityCard!).getAllByText("2개 계약에서 확인됐어요."),
  ).toHaveLength(2);

  const injuryDisclosure = within(medicalIndemnityCard!).getByRole("button", {
    name: /상해실손의료비/,
  });
  expect(injuryDisclosure).toHaveAttribute("aria-expanded", "false");

  await user.click(injuryDisclosure);
  expect(injuryDisclosure).toHaveAttribute("aria-expanded", "true");
  expect(
    within(medicalIndemnityCard!).getByText(
      "보험사A · 실손보험 A · 상해실손의료비",
    ),
  ).toBeInTheDocument();
  expect(
    within(medicalIndemnityCard!).getByText(
      "보험사B · 실손보험 B · 상해실손의료비",
    ),
  ).toBeInTheDocument();
  expect(
    within(actualLossReview!).queryByText(/상해실손의료비/),
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

test("disables repeated retries while the analysis is loading again", () => {
  render(<PortfolioAnalysisPanel {...baseProps()} status="error" isRetrying />);

  const retryButton = screen.getByRole("button", {
    name: "다시 확인하는 중…",
  });
  expect(retryButton).toBeDisabled();
  expect(retryButton).toHaveAttribute("aria-busy", "true");
});

test("explains when loading the analysis fails again", () => {
  render(
    <PortfolioAnalysisPanel {...baseProps()} status="error" retryFailed />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "다시 불러오지 못했어요. 업로드한 증권은 그대로 있으니",
  );
});
