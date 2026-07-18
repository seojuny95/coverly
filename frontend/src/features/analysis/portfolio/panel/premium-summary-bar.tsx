import { formatWon } from "../money-format";
import type { PortfolioSummary } from "../api";
import { ReferenceSourceList, sourceTypeLabel } from "../coverage-guide";

// Dark, semi-transparent pill styling (bg-white/5, border-white/10) is bespoke
// to this hero card and does not fit Card's white/zinc surface language.
export function PremiumSummaryBar({
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
