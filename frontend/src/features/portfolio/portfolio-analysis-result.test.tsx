import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PortfolioAnalysisResultView } from "./portfolio-analysis-result";
import type { PortfolioAnalysisResult } from "./portfolio-api";

const base: PortfolioAnalysisResult = {
  status: "complete",
  policy_count: 2,
  classification_count: 1,
  confirmed_total_count: 0,
  indemnity_coverage_count: 0,
  indemnity_duplicate_count: 1,
  excluded_coverage_count: 0,
  excluded_auto_policy_count: 0,
  age: 35,
  gender: "남성",
  life_stage: "사회초년기",
  prepared_coverages: ["암 진단비"],
  coverage_gaps: [{ category: "간병", reason: "확인되지 않았어요" }],
  excluded_coverages: [],
  premium: {
    monthly_total: 90_000,
    monthly_policy_count: 2,
    unconfirmed_policy_count: 0,
    items: [],
  },
  premium_benchmark: {
    age_band_label: "30대",
    min_age: 30,
    max_age: 39,
    average_monthly_premium: 278_395,
    source: {
      label: "KB의 생각 · 시그널플래너 40만명 분석",
      url: "https://kbthink.com/main/asset-management/insurance/insurance-2-240828.html",
      published_at: "2025-06-16",
      reliability: "large_private_analysis",
      caveat:
        "저축성보험을 제외한 2006년 이후 가입자의 월 평균 보험료로, 적정 보험료 기준은 아니에요.",
    },
  },
  baseline_notice: "일반 참고 기준이에요.",
  classifications: [],
  sources: [{ insurer: "삼성화재", product_name: "건강보험" }],
  notices: [],
};

describe("PortfolioAnalysisResultView", () => {
  it("renders the header with the insured name and headline metrics", () => {
    render(<PortfolioAnalysisResultView result={base} insuredName="가나" />);

    expect(screen.getByText(/Coverly AI가 가나님 편에서/)).toBeInTheDocument();
    expect(screen.getByText("35세 ·", { exact: false })).toBeInTheDocument();
    // formatWon(90000) appears in the headline metric and premium position card.
    expect(screen.getAllByText("90,000원").length).toBeGreaterThanOrEqual(1);
  });

  it("shows the monthly premium position against the age-band average", () => {
    render(<PortfolioAnalysisResultView result={base} />);

    expect(screen.getByText("내 보험료 위치")).toBeInTheDocument();
    expect(screen.getByText("30대 평균과 비교하면")).toBeInTheDocument();
    expect(screen.getByText("30대 평균")).toBeInTheDocument();
    expect(screen.getByText("278,395원")).toBeInTheDocument();
    expect(screen.getByText("평균보다 낮게 내고 있어요")).toBeInTheDocument();
    expect(
      screen.getByText(/KB의 생각 · 시그널플래너 40만명 분석/),
    ).toBeInTheDocument();
  });

  it("uses the full KB benchmark bands through age 70+", () => {
    render(
      <PortfolioAnalysisResultView
        result={{
          ...base,
          age: 72,
          premium: { ...base.premium, monthly_total: 210_000 },
          premium_benchmark: {
            ...base.premium_benchmark!,
            age_band_label: "70대 이상",
            min_age: 70,
            max_age: 120,
            average_monthly_premium: 193_168,
          },
        }}
      />,
    );

    expect(screen.getByText("70대 이상 평균과 비교하면")).toBeInTheDocument();
    expect(screen.getByText("70대 이상 평균")).toBeInTheDocument();
    expect(screen.getByText("193,168원")).toBeInTheDocument();
  });

  it("renders an unknown monthly premium without crashing", () => {
    render(
      <PortfolioAnalysisResultView
        result={{
          ...base,
          premium: { ...base.premium, monthly_total: null },
          premium_benchmark: null,
        }}
      />,
    );

    expect(screen.getByText("매달 내는 보험료")).toBeInTheDocument();
    expect(screen.getByText("미확인")).toBeInTheDocument();
    expect(screen.queryByText("내 보험료 위치")).not.toBeInTheDocument();
  });

  it("does not compare premiums when no monthly premium was confirmed", () => {
    render(
      <PortfolioAnalysisResultView
        result={{
          ...base,
          premium: {
            ...base.premium,
            monthly_total: 0,
            monthly_policy_count: 0,
          },
        }}
      />,
    );

    expect(screen.queryByText("내 보험료 위치")).not.toBeInTheDocument();
    expect(
      screen.queryByText("평균보다 낮게 내고 있어요"),
    ).not.toBeInTheDocument();
  });

  it("falls back to prepared_coverages / coverage_gaps without a counselor", () => {
    render(<PortfolioAnalysisResultView result={base} />);
    expect(screen.getByText("암 진단비")).toBeInTheDocument();
    expect(screen.getAllByText("간병")).toHaveLength(1);
    // fallback overview mentions the policy count
    expect(screen.getByText(/보험 2건에서/)).toBeInTheDocument();
  });

  it("prefers counselor strengths/gaps/overview when present", () => {
    const withCounselor: PortfolioAnalysisResult = {
      ...base,
      counselor: {
        overview: "전반적으로 잘 준비돼 있어요.",
        strengths: [
          {
            title: "실손 잘 가입됨",
            detail: "실손이 있어요",
            evidence_ids: [],
          },
        ],
        gaps: [
          {
            title: "간병 공백",
            detail: "지금 확인되지 않아요",
            evidence_ids: [],
          },
        ],
        amount_review_items: [],
        next_questions: ["간병은 어떻게 대비할까요?"],
        next_steps: [],
      },
    };
    render(<PortfolioAnalysisResultView result={withCounselor} />);

    expect(
      screen.getByText("전반적으로 잘 준비돼 있어요."),
    ).toBeInTheDocument();
    expect(screen.getByText("실손 잘 가입됨")).toBeInTheDocument();
    expect(screen.getAllByText("간병 공백")).toHaveLength(1);
    expect(screen.getByText("왜 의미가 있나요?")).toBeInTheDocument();
    expect(screen.getAllByText("왜 확인하나요?")).toHaveLength(1);
    expect(screen.getByText("보험을 한데 모아 보면")).toBeInTheDocument();
    // the prepared_coverages fallback is not used when counselor is present
    expect(screen.queryByText("암 진단비")).not.toBeInTheDocument();
  });

  it("does not show amount review items without supporting guidance data", () => {
    const withAmountReview: PortfolioAnalysisResult = {
      ...base,
      counselor: {
        overview: "확인된 보장을 정리했어요.",
        strengths: [],
        gaps: [],
        amount_review_items: [
          {
            coverage_name: "암진단비",
            current_amount: 40_000_000,
            title: "암진단비 금액을 살펴보세요",
            guidance: "개인 상황과 함께 봐야 해요.",
            rationale: "치료 중 생활비와 소득 공백을 함께 비교해야 해요.",
            suggested_range: null,
            confidence: "low",
            required_context: ["소득", "치료 중 생활비"],
            evidence_ids: ["coverage:1"],
          },
        ],
        next_questions: [],
        next_steps: [],
      },
    };

    render(<PortfolioAnalysisResultView result={withAmountReview} />);

    expect(screen.queryByText("가입금액 점검")).not.toBeInTheDocument();
    expect(screen.queryByText("암진단비")).not.toBeInTheDocument();
    expect(screen.queryByText("40,000,000원")).not.toBeInTheDocument();
  });

  it("shows cited policy and official sources in plain language without raw evidence", () => {
    const withEvidence: PortfolioAnalysisResult = {
      ...base,
      evidence: [
        {
          id: "coverage:1",
          fact: "암진단비 가입금액 합계 40,000,000원 확인",
          product_name: "건강보험",
          coverage_name: "암진단비",
          amount: 40_000_000,
        },
        {
          id: "official:1",
          fact: "사용자에게 그대로 보여주지 않을 어려운 약관 원문",
          publisher: "금융감독원",
          source_title: "표준약관",
          citation_label: "제3조",
        },
      ],
      counselor: {
        overview: "확인된 보장을 정리했어요.",
        strengths: [
          {
            title: "암진단비가 확인돼요",
            detail: "진단 초기 목돈을 살펴볼 수 있어요.",
            evidence_ids: ["coverage:1", "official:1"],
          },
        ],
        gaps: [],
        amount_review_items: [],
        next_questions: [],
        next_steps: [],
      },
    };

    render(<PortfolioAnalysisResultView result={withEvidence} />);

    expect(screen.getByText("근거 보기")).toBeInTheDocument();
    expect(
      screen.getByText(
        "건강보험에서 암진단비 가입금액 40,000,000원을 확인했어요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("금융감독원의 표준약관 제3조를 참고했어요."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("사용자에게 그대로 보여주지 않을 어려운 약관 원문"),
    ).not.toBeInTheDocument();
  });

  it("shows the overall summary once without review or reanalysis duplication", () => {
    const result: PortfolioAnalysisResult = {
      ...base,
      counselor: {
        overview: "확인된 보장을 정리했어요.",
        strengths: [],
        gaps: [
          {
            title: "사망 담보 확인",
            detail: "다른 증권에도 있는지 확인해보세요.",
            evidence_ids: ["gap:1"],
          },
        ],
        amount_review_items: [
          {
            coverage_name: "각막이식수술비",
            current_amount: 20_000_000,
            title: "각막이식수술비 금액 점검",
            guidance: "개인 상황과 함께 봐야 해요.",
            rationale: "치료비와 함께 비교해야 해요.",
            suggested_range: null,
            confidence: "low",
            evidence_ids: ["coverage:2"],
          },
          {
            coverage_name: "암진단비",
            current_amount: 40_000_000,
            title: "암진단비 금액 점검",
            guidance: "개인 상황과 함께 봐야 해요.",
            rationale: "생활비와 소득 공백을 함께 비교해야 해요.",
            suggested_range: null,
            confidence: "low",
            evidence_ids: ["coverage:1"],
          },
        ],
        next_questions: ["치료 중 필요한 생활비는 얼마인가요?"],
        next_steps: [],
      },
    };

    render(<PortfolioAnalysisResultView result={result} />);

    expect(screen.getByText("보험을 한데 모아 보면")).toBeInTheDocument();
    expect(screen.getByText("확인된 보장을 정리했어요.")).toBeInTheDocument();
    expect(screen.queryByText("점검 요약")).not.toBeInTheDocument();
    expect(screen.getAllByText("사망 담보 확인")).toHaveLength(1);
    expect(screen.queryByText(/가입금액/)).not.toBeInTheDocument();
    expect(screen.queryByText("내 상황을 알려주세요")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "답변으로 다시 분석하기" }),
    ).not.toBeInTheDocument();
  });

  it("does not show excluded data-limit items as additional checks", () => {
    const result: PortfolioAnalysisResult = {
      ...base,
      evidence: [
        {
          id: "excluded:1",
          coverage_name: "특정질환보장",
          fact: "지급 방식을 확인하지 못해 합계에는 더하지 않았어요.",
        },
      ],
      counselor: {
        overview: "확인된 보장을 정리했어요.",
        strengths: [],
        gaps: [
          {
            title: "지급 방식이 확인되지 않았어요",
            detail: "증권 정보가 부족해 합계에서 제외했어요.",
            evidence_ids: ["excluded:1"],
          },
        ],
        amount_review_items: [],
        next_questions: [],
        next_steps: [],
      },
    };

    render(<PortfolioAnalysisResultView result={result} />);

    expect(
      screen.queryByText("지급 방식이 확인되지 않았어요"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("현재 자료에서 추가로 확인할 항목을 찾지 못했어요."),
    ).toBeInTheDocument();
  });
});
