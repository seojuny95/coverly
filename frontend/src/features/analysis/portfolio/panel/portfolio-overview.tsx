import { Button } from "@/shared/components/ui/button";
import { formatWon } from "../money-format";
import type {
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  PortfolioSummary,
  SpecialPolicyAnalysis,
} from "../api";
import {
  RecommendedInsuranceCards,
  recommendedDiagnosisItems,
} from "../recommendation-cards";
import { ActualLossCoverageReview } from "./actual-loss-coverage-review";
import { PremiumSummaryBar } from "./premium-summary-bar";

export function PortfolioOverview({
  summary,
  items,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isDeathBenefitRefreshing,
  policyCount,
  specialAnalyses,
  onRetry,
}: {
  summary?: PortfolioSummary;
  items: EssentialCoverageItem[];
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isDeathBenefitRefreshing: boolean;
  policyCount: number;
  specialAnalyses: SpecialPolicyAnalysis[];
  onRetry: () => void;
}) {
  const diagnosisItems = recommendedDiagnosisItems(items);
  const confirmedDiagnosisCount = diagnosisItems.filter(
    (item) => item.status !== "not_found",
  ).length;
  const premium = summary?.premium ?? null;
  const premiumBenchmark = summary?.premium_benchmark ?? null;
  const hasPremiumReference = Boolean(
    premium &&
    premiumBenchmark &&
    typeof premium.monthly_total === "number" &&
    premium.monthly_policy_count > 0,
  );
  const generatedOverview = summary?.overview ?? null;

  if (!generatedOverview) {
    return (
      <section aria-labelledby="portfolio-overview-title" className="space-y-4">
        <div className="rounded-[28px] border border-zinc-200 bg-zinc-950 px-6 py-8 text-white sm:px-8">
          <p className="font-mono text-[11px] font-semibold tracking-[0.16em] text-blue-300 uppercase">
            전체 보험 총평
          </p>
          <h2
            id="portfolio-overview-title"
            className="mt-3 text-2xl font-semibold tracking-[-0.04em]"
          >
            총평을 생성하지 못했어요
          </h2>
          <p className="mt-3 text-sm leading-6 text-zinc-300">
            확인된 보장 정보는 그대로예요. 잠시 후 총평을 다시 생성해주세요.
          </p>
          <Button type="button" className="mt-5" onClick={onRetry}>
            총평 다시 생성하기
          </Button>
        </div>

        <RecommendedInsuranceCards
          items={items}
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={onDeathBenefitContextChange}
          isDeathBenefitRefreshing={isDeathBenefitRefreshing}
        />
        <ActualLossCoverageReview
          coverages={summary?.actual_loss_coverages ?? []}
        />
      </section>
    );
  }

  return (
    <section aria-labelledby="portfolio-overview-title" className="space-y-4">
      <div className="analysis-overview-reveal relative overflow-hidden rounded-[28px] border border-blue-200 bg-zinc-950 px-6 py-7 text-white shadow-[10px_10px_0_#e8edff] sm:px-8 sm:py-9">
        <div className="analysis-overview-grid pointer-events-none absolute inset-0" />
        <div className="relative">
          <div className="min-w-0">
            <p className="font-mono text-[11px] font-semibold tracking-[0.16em] text-blue-300 uppercase">
              전체 보험 총평
            </p>
            <h2
              id="portfolio-overview-title"
              className="mt-3 max-w-2xl text-2xl font-semibold tracking-[-0.045em] text-balance sm:text-3xl"
            >
              {generatedOverview.title}
            </h2>
            <div className="mt-4 max-w-3xl space-y-3 text-sm leading-7 text-pretty text-zinc-300">
              {(generatedOverview.paragraphs ?? []).map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>

            <div className="mt-6 flex flex-wrap gap-2 border-t border-white/10 pt-5 text-xs text-zinc-300">
              {hasPremiumReference ? (
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                  월 보험료 {formatWon(premium?.monthly_total ?? null)}
                </span>
              ) : null}
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                올린 증권 {policyCount}건
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                3대 진단비 {confirmedDiagnosisCount}/3
              </span>
              {specialAnalyses.length > 0 ? (
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                  손해보험 {specialAnalyses.length}종
                </span>
              ) : null}
            </div>

            {hasPremiumReference ? (
              <PremiumSummaryBar
                premium={premium}
                benchmark={premiumBenchmark}
              />
            ) : null}
          </div>
        </div>
      </div>

      <RecommendedInsuranceCards
        items={items}
        deathBenefitContext={deathBenefitContext}
        onDeathBenefitContextChange={onDeathBenefitContextChange}
        isDeathBenefitRefreshing={isDeathBenefitRefreshing}
      />
      <ActualLossCoverageReview
        coverages={summary?.actual_loss_coverages ?? []}
      />
    </section>
  );
}
