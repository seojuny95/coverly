import { Button } from "../../../shared/components/ui/button";
import { ClaimGuide } from "./claim-guide";
import { formatWon } from "./money-format";
import type {
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  PortfolioSummary,
  SpecialPolicyAnalysis,
} from "./api";
import { ReferenceSourceList, sourceTypeLabel } from "./coverage-guide";
import {
  RecommendedInsuranceCards,
  recommendedDiagnosisItems,
} from "./recommendation-cards";
import { SpecialPolicySections } from "./special-policy-sections";

export function PortfolioAnalysisPanel({
  status,
  summary,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isDeathBenefitRefreshing = false,
  policyCount,
  onRetry,
}: {
  status: "loading" | "success" | "error";
  summary?: PortfolioSummary;
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isDeathBenefitRefreshing?: boolean;
  policyCount: number;
  onRetry: () => void;
}) {
  if (status === "loading") return <AnalysisLoading />;

  if (status === "error") {
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">
          보장 점검 결과를 불러오지 못했어요
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          업로드한 증권은 그대로 있어요. 잠시 후 다시 확인해주세요.
        </p>
        <Button type="button" className="mt-5" onClick={onRetry}>
          다시 확인하기
        </Button>
      </section>
    );
  }

  const items = summary?.essential_coverage_check?.items ?? [];
  const specialAnalyses = summary?.special_policy_analyses ?? [];

  return (
    <div className="space-y-8">
      <PortfolioOverview
        summary={summary}
        items={items}
        deathBenefitContext={deathBenefitContext}
        onDeathBenefitContextChange={onDeathBenefitContextChange}
        isDeathBenefitRefreshing={isDeathBenefitRefreshing}
        policyCount={policyCount}
        specialAnalyses={specialAnalyses}
        onRetry={onRetry}
      />

      {specialAnalyses.length > 0 ? (
        <SpecialPolicySections analyses={specialAnalyses} />
      ) : null}

      <ClaimGuide claimChannels={summary?.claim_channels ?? null} />
    </div>
  );
}

function PortfolioOverview({
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

            <div className="mt-6 grid gap-3 border-y border-white/10 py-4 text-sm sm:grid-cols-3">
              {(generatedOverview.takeaways ?? []).map((takeaway) => (
                <div key={takeaway.label} className="min-w-0">
                  <p className="text-[11px] font-semibold tracking-[0.12em] text-blue-300 uppercase">
                    {takeaway.label}
                  </p>
                  <p className="mt-1 font-semibold text-white">
                    {takeaway.title}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-zinc-400">
                    {takeaway.detail}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-5 flex flex-wrap gap-2 text-xs text-zinc-300">
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

function duplicateActualLossCoverageNames(
  coverages: PortfolioSummary["actual_loss_coverages"],
) {
  const namesByNormalizedName = new Map<string, string>();
  for (const coverage of coverages) {
    if (!coverage.duplicate_across_contracts) continue;
    const key = coverage.normalized_name || coverage.coverage_name;
    if (!namesByNormalizedName.has(key)) {
      namesByNormalizedName.set(key, coverage.coverage_name);
    }
  }
  return [...namesByNormalizedName.values()];
}

function ActualLossCoverageReview({
  coverages,
}: {
  coverages: PortfolioSummary["actual_loss_coverages"];
}) {
  const duplicateNames = duplicateActualLossCoverageNames(coverages);

  return (
    <article className="analysis-overview-reveal analysis-overview-delay-2 rounded-2xl border border-zinc-200 bg-white p-5 sm:p-6">
      <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
        계약별 확인 결과
      </p>
      <h3 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
        여러 계약에 표시된 담보
      </h3>
      {duplicateNames.length > 0 ? (
        <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
          여러 계약에 표시된 담보: {duplicateNames.join(" · ")}
        </p>
      ) : coverages.length > 0 ? (
        <p className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-600">
          여러 계약에 함께 표시된 담보는 없어요.
        </p>
      ) : (
        <p className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-600">
          현재 자료에서 계약별로 비교할 담보가 없어요.
        </p>
      )}
    </article>
  );
}

function PremiumSummaryBar({
  premium,
  benchmark,
}: {
  premium: PortfolioSummary["premium"];
  benchmark: PortfolioSummary["premium_benchmark"];
}) {
  if (
    !premium ||
    !benchmark ||
    typeof premium.monthly_total !== "number" ||
    premium.monthly_policy_count < 1
  ) {
    return null;
  }

  const sourceLabels = [
    sourceTypeLabel(benchmark.income_source.reliability),
    sourceTypeLabel(benchmark.guide_source.reliability),
  ];

  return (
    <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold text-blue-200">현재 월 보험료</p>
          <p className="mt-1 text-lg font-semibold tracking-[-0.03em] text-white">
            {formatWon(premium.monthly_total)}
          </p>
        </div>
        <div className="sm:text-right">
          <p className="text-xs text-zinc-400">
            {benchmark.age_band_label} 참고 구간
          </p>
          <p className="mt-1 text-sm font-medium text-zinc-200">
            {formatWon(benchmark.suggested_min_premium)} ~{" "}
            {formatWon(benchmark.suggested_max_premium)}
          </p>
        </div>
      </div>

      <p className="mt-3 text-xs leading-5 text-zinc-300">
        월 소득의 {Math.round(benchmark.suggested_min_ratio * 100)}%~
        {Math.round(benchmark.suggested_max_ratio * 100)}%에 해당하는 참고
        금액이에요. {sourceLabels.join(" + ")} 자료를 사용했어요.
      </p>
      <ReferenceSourceList
        sources={[benchmark.income_source, benchmark.guide_source]}
        className="[&_a]:border-white/10 [&_a]:bg-white/10 [&_a]:text-zinc-200 [&_span]:border-white/10 [&_span]:bg-white/10 [&_span]:text-zinc-200"
      />
    </div>
  );
}

function AnalysisLoading() {
  return (
    <section
      aria-live="polite"
      aria-busy="true"
      className="rounded-2xl border border-zinc-200 p-8"
    >
      <div className="h-2 w-20 animate-pulse rounded bg-blue-600" />
      <h2 className="mt-5 text-xl font-semibold">
        전체 보험의 핵심 보장을 확인하고 있어요
      </h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">
        사망·3대 진단비·실손의료비와 보험 종류별 담보를 정리하고 있어요.
      </p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((item) => (
          <div
            key={item}
            className="h-40 animate-pulse rounded-xl bg-zinc-100"
          />
        ))}
      </div>
    </section>
  );
}
