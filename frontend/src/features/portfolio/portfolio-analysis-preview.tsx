"use client";

import { useState } from "react";

import { CoverlyLogo, PixelEyebrow } from "../../components/coverly-brand";
import { PortfolioAnalysisPanel } from "./portfolio-analysis-panel";
import type { DeathBenefitGuideInput, PortfolioSummary } from "./portfolio-api";

const DEATH_BENEFIT_SOURCE = {
  label: "매일경제 · 가장의 적정 사망보험금은 연소득 3~5배",
  url: "https://www.mk.co.kr/news/economy/9495174",
  published_at: "2020-08-28",
  reliability: "private_guidance" as const,
  caveat: "민간 재무설계 관점의 일반 가이드예요.",
};
const BIZWATCH_DIAGNOSIS_SOURCE = {
  label: "비즈워치 · 암 진단비 평균 범위",
  url: "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
  published_at: "2024-07-06",
  reliability: "private_guidance" as const,
  caveat:
    "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요.",
};
const BANKSALAD_DIAGNOSIS_SOURCE = {
  label: "뱅크샐러드 · 3대 진단비 구성 예시",
  url: "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EC%A2%85%ED%95%A9%EB%B3%B4%ED%97%98-%EC%A7%88%EB%B3%B4%ED%97%98",
  published_at: "2026-07-01",
  reliability: "private_guidance" as const,
  caveat: "구성 예시는 상품과 개인 상황에 따라 달라질 수 있어요.",
};
const MEDICAL_INDEMNITY_SOURCE = {
  label: "실손24 · 서비스 안내",
  url: "https://www.silson24.or.kr",
  published_at: "2025-01-01",
  reliability: "official" as const,
  caveat:
    "실손의료비 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요.",
};

const PREVIEW_SUMMARY: PortfolioSummary = {
  totals: [],
  actual_loss_coverages: [
    {
      policy_id: "health-1",
      insurer: "삼성화재",
      product_name: "건강보험",
      coverage_name: "질병실손의료비",
      normalized_name: "질병실손의료비",
      coverage_domain: "medical_expense",
      is_medical_indemnity: true,
      is_damage_policy: false,
      duplicate_across_contracts: true,
    },
    {
      policy_id: "health-2",
      insurer: "메리츠화재",
      product_name: "실손의료보험",
      coverage_name: "질병실손의료비",
      normalized_name: "질병실손의료비",
      coverage_domain: "medical_expense",
      is_medical_indemnity: true,
      is_damage_policy: false,
      duplicate_across_contracts: true,
    },
  ],
  excluded_coverages: [],
  excluded_auto_policy_count: 0,
  overview: {
    generation: "llm",
    title: "권장보험을 먼저 점검해보세요",
    paragraphs: [
      "월납으로 확인된 보험료는 98,000원으로, 20~30대 평균 소득 기준 권장 범위보다 낮아요. 보험료가 낮은 것 자체는 문제가 아니지만, 뇌혈관질환과 심장질환 진단비가 현재 자료에서 보이지 않아 권장보험 항목을 먼저 점검해야 해요.",
      "사망 보장과 암 진단비, 실손의료보험은 확인됐고, 실손 보장은 여러 계약에서 보여 중복 여부를 따로 볼 필요가 있어요. 자동차·운전자·여행자·화재보험은 담보명이 확인된 범위 안에서 주요 보장 영역을 나눠 정리했어요.",
      "이 총평은 업로드한 증권에서 읽은 담보명, 가입금액, 월 보험료를 바탕으로 만든 1차 해석이에요. 실제 충분성은 소득, 부양가족, 대출, 병력, 약관의 면책·감액·갱신 조건까지 함께 확인해야 해요.",
    ],
    takeaways: [
      {
        label: "보험료",
        title: "권장보험을 점검해보세요",
        detail: "보험료가 낮은 이유가 핵심 보장 공백일 수 있어요.",
      },
      {
        label: "보장 구성",
        title: "3/5개 확인",
        detail:
          "뇌혈관질환 진단비 · 심장질환 진단비 항목은 현재 자료에서 미확인이에요.",
      },
      {
        label: "다음 확인",
        title: "미확인 보장 확인",
        detail: "다른 증권, 특약명, 가입설계서에 빠진 보장이 있는지 봐요.",
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
        reference_sources: [DEATH_BENEFIT_SOURCE],
        reference_amount_label: "0원~5천만 원",
        guidance_situation: "부양가족이나 큰 부채가 없는 경우",
        guidance_reason:
          "사망보험금은 남은 가족의 생활비 공백을 메우는 목적이 크기 때문에, 부양가족이나 큰 부채가 없다면 큰 금액의 필요성은 낮아요. 장례비, 정리비, 부모 지원 정도만 고려하면 돼요.",
        coverage_count: 1,
        detail: "사망 담보가 확인돼요.",
        matched_coverage_names: ["질병사망"],
      },
      {
        kind: "cancer",
        label: "암 진단비",
        status: "well_prepared",
        confirmed_amount: 35_000_000,
        reference_min_amount: 30_000_000,
        reference_max_amount: 50_000_000,
        reference_basis:
          "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
        reference_sources: [
          BIZWATCH_DIAGNOSIS_SOURCE,
          BANKSALAD_DIAGNOSIS_SOURCE,
        ],
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
        reference_min_amount: 10_000_000,
        reference_max_amount: 20_000_000,
        reference_basis:
          "뇌혈관질환 진단비는 재활, 간병, 후유장해 가능성을 고려하는 기본 범위",
        reference_sources: [BANKSALAD_DIAGNOSIS_SOURCE],
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
        reference_sources: [BANKSALAD_DIAGNOSIS_SOURCE],
        coverage_count: 0,
        detail: "현재 올린 전체 보험에서는 확인하지 못했어요.",
        matched_coverage_names: [],
      },
      {
        kind: "medical_indemnity",
        label: "실손의료보험",
        status: "needs_review",
        confirmed_amount: null,
        reference_min_amount: null,
        reference_max_amount: null,
        reference_basis:
          "실손의료보험은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인",
        reference_sources: [MEDICAL_INDEMNITY_SOURCE],
        coverage_count: 2,
        detail:
          "실손의료보험이 여러 계약에서 확인돼요. 중복 가입 여부를 확인해보세요.",
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
        "상대방의 신체 피해, 상대방의 재물 피해는 확인돼요. 운전자·탑승자 상해, 내 차량 손해, 무보험차 사고 상해는 현재 자료에서 찾지 못했으며, 이것만으로 미가입이라고 단정할 수는 없어요.",
      coverage_checks: [
        {
          label: "상대방의 신체 피해",
          status: "confirmed",
          detail: "사고로 다른 사람이 다치거나 사망했을 때의 배상 담보예요.",
          matched_coverage_names: ["대인배상Ⅰ"],
        },
        {
          label: "상대방의 재물 피해",
          status: "confirmed",
          detail:
            "사고로 다른 사람의 차량이나 재물에 생긴 손해를 배상하는 담보예요.",
          matched_coverage_names: ["대물배상"],
        },
        {
          label: "운전자·탑승자 상해",
          status: "not_found",
          detail: "운전자나 탑승자가 다쳤을 때를 위한 담보예요.",
          matched_coverage_names: [],
        },
        {
          label: "내 차량 손해",
          status: "not_found",
          detail: "가입 차량에 생긴 손해를 위한 담보예요.",
          matched_coverage_names: [],
        },
        {
          label: "무보험차 사고 상해",
          status: "not_found",
          detail: "무보험 차량과의 사고로 다쳤을 때를 위한 담보예요.",
          matched_coverage_names: [],
        },
      ],
    },
    {
      kind: "driver",
      label: "운전자보험",
      policy_count: 1,
      product_names: ["안심 운전자보험"],
      confirmed_coverage_names: ["교통사고처리지원금", "변호사선임비용"],
      overview:
        "교통사고 처리 지원, 변호사 선임 비용은 확인돼요. 운전자 벌금은 현재 자료에서 찾지 못했으며, 이것만으로 미가입이라고 단정할 수는 없어요.",
      coverage_checks: [
        {
          label: "교통사고 처리 지원",
          status: "confirmed",
          detail: "형사합의가 필요한 교통사고의 비용 부담을 위한 담보예요.",
          matched_coverage_names: ["교통사고처리지원금"],
        },
        {
          label: "변호사 선임 비용",
          status: "confirmed",
          detail: "교통사고 형사 절차에서 변호사를 선임할 때를 위한 담보예요.",
          matched_coverage_names: ["변호사선임비용"],
        },
        {
          label: "운전자 벌금",
          status: "not_found",
          detail: "교통사고로 확정된 벌금 비용을 위한 담보예요.",
          matched_coverage_names: [],
        },
      ],
    },
    {
      kind: "travel",
      label: "여행자보험",
      policy_count: 1,
      product_names: ["해외여행보험"],
      confirmed_coverage_names: ["해외의료비", "휴대품손해"],
      overview:
        "해외 의료비, 휴대품 손해는 확인돼요. 여행 중 배상책임, 항공기 지연·여행 취소는 현재 자료에서 찾지 못했으며, 이것만으로 미가입이라고 단정할 수는 없어요.",
      coverage_checks: [
        {
          label: "해외 의료비",
          status: "confirmed",
          detail:
            "여행 중 질병이나 상해로 해외에서 지출한 의료비를 위한 담보예요.",
          matched_coverage_names: ["해외의료비"],
        },
        {
          label: "휴대품 손해",
          status: "confirmed",
          detail: "여행 중 휴대품의 도난이나 파손을 위한 담보예요.",
          matched_coverage_names: ["휴대품손해"],
        },
        {
          label: "여행 중 배상책임",
          status: "not_found",
          detail: "여행 중 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
          matched_coverage_names: [],
        },
        {
          label: "항공기 지연·여행 취소",
          status: "not_found",
          detail: "항공편 지연이나 여행 취소로 생긴 약정 비용을 위한 담보예요.",
          matched_coverage_names: [],
        },
      ],
    },
    {
      kind: "fire",
      label: "화재보험",
      policy_count: 1,
      product_names: ["우리집 화재보험"],
      confirmed_coverage_names: ["화재손해", "가족일상생활배상책임"],
      overview:
        "건물·가재 화재 손해는 확인돼요. 화재 배상책임, 임시 거주·복구 비용은 현재 자료에서 찾지 못했으며, 이것만으로 미가입이라고 단정할 수는 없어요.",
      coverage_checks: [
        {
          label: "건물·가재 화재 손해",
          status: "confirmed",
          detail: "화재로 건물이나 가재도구에 생긴 직접 손해를 위한 담보예요.",
          matched_coverage_names: ["화재손해"],
        },
        {
          label: "화재 배상책임",
          status: "not_found",
          detail: "화재로 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
          matched_coverage_names: [],
        },
        {
          label: "임시 거주·복구 비용",
          status: "not_found",
          detail: "화재 뒤 임시 거주나 잔존물 제거·복구 비용을 위한 담보예요.",
          matched_coverage_names: [],
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
        links: [
          { label: "청구 링크", url: "https://www.meritzfire.com" },
          { label: "홈페이지", url: "https://www.meritzfire.com" },
        ],
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
    unconfirmed_policy_count: 2,
    items: [
      {
        policy_id: "health-1",
        insurer: "삼성화재",
        product_name: "건강보험",
        monthly_amount: 42_000,
        cycle: "월납",
      },
      {
        policy_id: "health-2",
        insurer: "메리츠화재",
        product_name: "실손의료보험",
        monthly_amount: 31_000,
        cycle: "월납",
      },
      {
        policy_id: "driver-1",
        insurer: "DB손해보험",
        product_name: "운전자보험",
        monthly_amount: 25_000,
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

export function PortfolioAnalysisPreview() {
  const [deathBenefitContext, setDeathBenefitContext] =
    useState<DeathBenefitGuideInput>({
      has_dependent_family: false,
      has_minor_children: false,
      has_major_debt: false,
    });

  return (
    <main className="min-h-dvh bg-white px-5 py-6 text-zinc-950 sm:px-6">
      <div className="mx-auto w-full max-w-6xl">
        <CoverlyLogo />
        <header className="mt-10 mb-7">
          <PixelEyebrow>내 보험 분석 · 샘플 미리보기</PixelEyebrow>
          <h1 className="mt-4 text-3xl font-semibold tracking-[-0.05em] text-balance sm:text-4xl">
            가입한 보험을 한눈에 확인해요
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            샘플 데이터로 디자인과 애니메이션을 확인하는 개발 전용 화면이에요.
          </p>
        </header>

        <PortfolioAnalysisPanel
          status="success"
          summary={PREVIEW_SUMMARY}
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={setDeathBenefitContext}
          isDeathBenefitRefreshing={false}
          eligibleCount={5}
          emptyReason="no-coverage"
          onRetry={() => undefined}
        />
      </div>
    </main>
  );
}
