import { Alert } from "../../../../shared/components/ui/alert";
import { Card } from "../../../../shared/components/ui/card";
import type { PortfolioSummary } from "../api";

// Kept as a native <article> (not <Card>, which renders a div) so the
// section-level semantics survive for assistive tech and existing tests.

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

export function ActualLossCoverageReview({
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
        <Alert
          variant="warning"
          className="mt-4 rounded-2xl border-amber-200 px-4 py-3 text-sm leading-6 text-amber-800"
        >
          여러 계약에 표시된 담보: {duplicateNames.join(" · ")}
        </Alert>
      ) : coverages.length > 0 ? (
        <Card
          variant="muted"
          className="mt-4 px-4 py-3 text-sm leading-6 text-zinc-600"
        >
          여러 계약에 함께 표시된 담보는 없어요.
        </Card>
      ) : (
        <Card
          variant="muted"
          className="mt-4 px-4 py-3 text-sm leading-6 text-zinc-600"
        >
          현재 자료에서 계약별로 비교할 담보가 없어요.
        </Card>
      )}
    </article>
  );
}
