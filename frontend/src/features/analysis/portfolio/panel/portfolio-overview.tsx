import { RetryButton } from "@/shared/components/retry-button";
import { Skeleton } from "@/shared/components/ui/skeleton";
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
  isRetrying,
  retryFailed,
}: {
  summary?: PortfolioSummary;
  items: EssentialCoverageItem[];
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isDeathBenefitRefreshing: boolean;
  policyCount: number;
  specialAnalyses: SpecialPolicyAnalysis[];
  onRetry: () => void;
  isRetrying: boolean;
  retryFailed: boolean;
}) {
  const diagnosisItems = recommendedDiagnosisItems(items);
  const confirmedDiagnosisCount = diagnosisItems.filter(
    (item) => item.status !== "not_found",
  ).length;
  const premium = summary?.premium ?? null;
  const premiumBenchmark = summary?.premium_benchmark ?? null;
  const hasPremium = Boolean(
    premium &&
    typeof premium.monthly_total === "number" &&
    premium.monthly_policy_count > 0,
  );
  const generatedOverview = summary?.overview ?? null;

  return (
    <section aria-labelledby="portfolio-overview-title" className="space-y-4">
      <div className="animate-enter relative overflow-hidden rounded-[28px] border border-blue-200 bg-zinc-950 px-6 py-7 text-white shadow-[10px_10px_0_#e8edff] sm:px-8 sm:py-9">
        <div className="analysis-overview-grid pointer-events-none absolute inset-0" />
        <div className="relative">
          <div className="min-w-0">
            <p className="font-mono text-[11px] font-semibold tracking-[0.16em] text-blue-300 uppercase">
              전체 보험 총평
            </p>
            <PortfolioOverviewCopy
              overview={generatedOverview}
              isRetrying={isRetrying}
              retryFailed={retryFailed}
              onRetry={onRetry}
            />

            <div className="mt-6 flex flex-wrap gap-2 border-t border-white/10 pt-5 text-xs text-zinc-300">
              {hasPremium ? (
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

            {hasPremium ? (
              <PremiumSummaryBar
                premium={premium}
                benchmark={premiumBenchmark}
              />
            ) : null}
          </div>
        </div>
      </div>

      <RecommendedInsuranceCards
        actualLossCoverages={summary?.actual_loss_coverages ?? []}
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

function PortfolioOverviewCopy({
  overview,
  isRetrying,
  retryFailed,
  onRetry,
}: {
  overview: PortfolioSummary["overview"];
  isRetrying: boolean;
  retryFailed: boolean;
  onRetry: () => void;
}) {
  if (overview) {
    return (
      <div className="animate-enter" aria-live="polite">
        <h2
          id="portfolio-overview-title"
          className="mt-3 max-w-2xl text-2xl font-semibold tracking-[-0.045em] text-balance sm:text-3xl"
        >
          {overview.title}
        </h2>
        <div className="mt-4 max-w-3xl space-y-3 text-sm leading-7 text-pretty text-zinc-300">
          {(overview.paragraphs ?? []).map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
      </div>
    );
  }

  if (!retryFailed || isRetrying) {
    return (
      <div role="status" aria-live="polite">
        <h2
          id="portfolio-overview-title"
          className="mt-3 text-2xl font-semibold tracking-[-0.04em]"
        >
          총평을 정리하고 있어요
        </h2>
        <p className="mt-3 text-sm leading-6 text-zinc-300">
          확인된 보장과 보험료 정보는 먼저 볼 수 있어요. 총평 문장만 이어서
          준비하고 있어요.
        </p>
        <div
          aria-hidden="true"
          className="mt-5 max-w-3xl space-y-2.5 rounded-2xl border border-white/10 bg-white/[0.035] p-4"
        >
          <Skeleton className="h-2.5 w-full bg-white/10" />
          <Skeleton className="h-2.5 w-11/12 bg-white/10" />
          <Skeleton className="h-2.5 w-3/4 bg-white/10" />
        </div>
      </div>
    );
  }

  return (
    <>
      <h2
        id="portfolio-overview-title"
        className="mt-3 text-2xl font-semibold tracking-[-0.04em]"
      >
        총평을 생성하지 못했어요
      </h2>
      <p role="alert" className="mt-3 text-sm leading-6 text-zinc-300">
        총평 문장만 생성하지 못했어요. 확인된 보장과 보험료 정보는 그대로 확인할
        수 있으니 잠시 후 다시 시도해주세요.
      </p>
      <RetryButton
        type="button"
        className="mt-5"
        onClick={onRetry}
        isPending={false}
        label="총평 다시 생성하기"
        pendingLabel="총평 다시 생성하는 중…"
      />
    </>
  );
}
