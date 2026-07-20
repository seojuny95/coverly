import { Alert } from "@/shared/components/ui/alert";
import { Card } from "@/shared/components/ui/card";
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
    <article className="animate-enter rounded-2xl border border-zinc-200 bg-white p-5 delay-200 sm:p-6">
      <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
        실손형 보장 중복 확인
      </p>
      <h3 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
        여러 계약에 겹쳐 있는 보장
      </h3>
      <p className="mt-2 text-sm leading-6 text-zinc-600">
        실제로 발생한 손해만큼 보상하는 담보가 여러 계약에 함께 있는지 확인해요.
      </p>
      {duplicateNames.length > 0 ? (
        <Alert
          variant="warning"
          role="note"
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
