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
    age_band_label: "30~39세",
    min_age: 30,
    max_age: 39,
    average_monthly_income: 3_860_000,
    suggested_min_ratio: 0.05,
    suggested_max_ratio: 0.1,
    suggested_min_premium: 193_000,
    suggested_max_premium: 386_000,
    income_source: {
      label: "KOSIS 국가통계포털 · 성별 연령대별 소득",
      url: "https://kosis.kr/statHtml/statHtml.do?sso=ok&returnurl=https%3A%2F%2Fkosis.kr%3A443%2FstatHtml%2FstatHtml.do%3Fconn_path%3DI2%26tblId%3DDT_1EP_2010%26orgId%3D101%26",
      published_at: "2025-01-01",
      reliability: "official",
      caveat: "연령대 평균 소득은 개인 소득과 다를 수 있어요.",
    },
    guide_source: {
      label: "뱅크샐러드 · 나에게 맞는 보험료 계산법",
      url: "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-%EB%B3%B4%ED%97%98%EB%A3%8C",
      published_at: "2025-01-01",
      reliability: "private_guidance",
      caveat:
        "월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.",
    },
  },
  age_coverage_recommendation: {
    age_band_label: "30~39세",
    title: "실손 + 3대 진단비를 먼저 보는 구간이에요",
    detail:
      "30~39세 기준 기본 항목 4개 중 3개가 확인돼요. 나머지는 다른 증권에 있는지 한 번 더 보면 좋아요.",
    confirmed_count: 3,
    recommended_count: 4,
    optional_count: 0,
    items: [
      {
        category: "실손의료",
        status: "confirmed",
        title: "실손의료 성격 보장이 확인돼요",
        detail: "현재 올린 증권에서 이 항목이 보여요.",
        evidence_ids: [],
      },
      {
        category: "암 진단",
        status: "confirmed",
        title: "암 진단 성격 보장이 확인돼요",
        detail: "현재 올린 증권에서 이 항목이 보여요.",
        evidence_ids: [],
      },
      {
        category: "뇌혈관 진단",
        status: "confirmed",
        title: "뇌혈관 진단 성격 보장이 확인돼요",
        detail: "현재 올린 증권에서 이 항목이 보여요.",
        evidence_ids: [],
      },
      {
        category: "심장질환 진단",
        status: "missing",
        title: "심장질환 진단 성격 보장은 아직 확인되지 않았어요",
        detail:
          "이 연령대에서 함께 보는 기본 준비 묶음에는 들어가지만, 현재 올린 증권에서는 찾지 못했어요.",
        evidence_ids: [],
      },
    ],
    source: {
      label: "뱅크샐러드 · 연령별 필수 보험 가이드",
      url: "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-%EB%B3%B4%ED%97%98%EB%A3%8C",
      published_at: "2025-01-01",
      reliability: "private_guidance",
      caveat:
        "민간 가이드예요. 가입 권유나 개인별 충분·부족 판정 기준은 아니에요.",
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

  it("shows the monthly premium position against the age-band income guide", () => {
    render(<PortfolioAnalysisResultView result={base} />);

    expect(
      screen.getAllByText("매달 내는 보험료").length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText("내 보험료가 참고 범위 어디쯤인지 볼게요"),
    ).toBeInTheDocument();
    expect(screen.getByText("30~39세 평균 소득 기준")).toBeInTheDocument();
    expect(
      screen.getByText("참고 범위 193,000원 ~ 386,000원"),
    ).toBeInTheDocument();
    expect(screen.getByText("참고 범위보다 낮아요")).toBeInTheDocument();
    expect(
      screen.getByText(/KOSIS 국가통계포털 · 성별 연령대별 소득/),
    ).toBeInTheDocument();
  });

  it("does not render internal priority checks as a separate section", () => {
    render(
      <PortfolioAnalysisResultView
        result={{
          ...base,
          priority_checks: [
            {
              kind: "premium",
              title: "월 보험료가 소득 기준 참고 범위보다 낮아요",
              detail:
                "낮다고 부족하다는 뜻은 아니지만 큰 보장은 함께 확인해야 해요.",
              evidence_ids: [],
            },
            {
              kind: "coverage_gap",
              title: "간병 보장이 다른 증권에 있는지 확인하세요",
              detail: "현재 올린 보험에서는 찾지 못했어요.",
              evidence_ids: ["gap:1"],
            },
          ],
          evidence: [
            {
              id: "gap:1",
              coverage_name: "간병",
              fact: "업로드된 비자동차 보험 전체에서 간병 담보를 확인하지 못함",
            },
          ],
        }}
      />,
    );

    expect(screen.queryByText("우선 확인 3가지")).not.toBeInTheDocument();
    expect(
      screen.queryByText("월 보험료가 소득 기준 참고 범위보다 낮아요"),
    ).not.toBeInTheDocument();
  });

  it("shows claim conditions and relevant policy changes without amount status", () => {
    render(
      <PortfolioAnalysisResultView
        result={{
          ...base,
          coverage_amount_status: {
            title: "확인된 보장금액만 먼저 모았어요",
            detail: "충분하거나 부족하다는 뜻은 아니에요.",
            confirmed_total_amount: 30_000_000,
            confirmed_category_count: 1,
            unconfirmed_coverage_count: 1,
            items: [
              {
                category: "암 진단비",
                amount: 30_000_000,
                coverage_count: 1,
                title: "암 진단비 30,000,000원 확인",
                detail: "숫자로 확인된 금액을 합산했어요.",
                evidence_ids: ["coverage:1"],
              },
            ],
          },
          claim_condition_checks: [
            {
              kind: "fixed",
              title: "정액형 보장은 지급사유와 감액기간을 확인하세요",
              detail: "진단확정, 면책기간, 감액기간 조건을 확인해야 해요.",
              evidence_ids: ["coverage:1"],
            },
          ],
          policy_change_checks: [
            {
              title: "실손보험 청구 전산화가 의원·약국까지 확대 예정이에요",
              summary: "서류 전송을 요청하면 전자문서가 전달되는 방식이에요.",
              user_impact:
                "실손 담보가 있다면 청구를 놓치지 않았는지 보기 쉬워질 수 있어요.",
              effective_from: "2025-10-25",
              applies_to: "의원급 의료기관과 약국의 실손보험 청구",
              source: {
                label: "금융위원회 · 실손보험 청구 전산화 카드뉴스",
                url: "https://www.fsc.go.kr/edu/cardnews?cnId=1976",
                published_at: "2023-11-20",
                reliability: "official",
                caveat: "의료기관 참여 여부에 따라 달라질 수 있어요.",
              },
            },
          ],
          evidence: [
            {
              id: "coverage:1",
              coverage_name: "암 진단비",
              amount: 30_000_000,
              product_name: "건강보험",
            },
          ],
        }}
      />,
    );

    expect(screen.queryByText("보장금액 상태")).not.toBeInTheDocument();
    expect(screen.getByText("받을 때 확인할 조건")).toBeInTheDocument();
    expect(screen.getByText("최근 제도 변화")).toBeInTheDocument();
    expect(
      screen.getByText("실손보험 청구 전산화가 의원·약국까지 확대 예정이에요"),
    ).toBeInTheDocument();
  });

  it("does not render age-band recommendation as a separate section", () => {
    render(<PortfolioAnalysisResultView result={base} />);

    expect(screen.queryByText("연령대 기준 준비 상태")).not.toBeInTheDocument();
    expect(
      screen.queryByText("실손 + 3대 진단비를 먼저 보는 구간이에요"),
    ).not.toBeInTheDocument();
  });

  it("uses the income guide bands through age 60+", () => {
    render(
      <PortfolioAnalysisResultView
        result={{
          ...base,
          age: 68,
          premium: { ...base.premium, monthly_total: 210_000 },
          premium_benchmark: {
            ...base.premium_benchmark!,
            age_band_label: "60세 이상",
            min_age: 60,
            max_age: 120,
            average_monthly_income: 2_500_000,
            suggested_min_premium: 125_000,
            suggested_max_premium: 250_000,
          },
        }}
      />,
    );

    expect(screen.getByText("60세 이상 평균 소득 기준")).toBeInTheDocument();
    expect(
      screen.getByText("참고 범위 125,000원 ~ 250,000원"),
    ).toBeInTheDocument();
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
    expect(screen.queryByText("참고 범위보다 낮아요")).not.toBeInTheDocument();
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
