import { Alert } from "@/shared/components/ui/alert";
import { Card } from "@/shared/components/ui/card";

import { duplicateActualLossCoverageGroups } from "../actual-loss-coverage-groups";
import type { PortfolioSummary } from "../api";

// Kept as a native <article> (not <Card>, which renders a div) so the
// section-level semantics survive for assistive tech and existing tests.
export function ActualLossCoverageReview({
  coverages,
}: {
  coverages: PortfolioSummary["actual_loss_coverages"];
}) {
  const nonMedicalCoverages = coverages.filter(
    (coverage) => !coverage.is_medical_indemnity,
  );
  const duplicateGroups =
    duplicateActualLossCoverageGroups(nonMedicalCoverages);

  return (
    <article className="animate-enter rounded-2xl border border-zinc-200 bg-white p-5 delay-200 sm:p-6">
      <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
        실손형 보장 중복 확인
      </p>
      <h3 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
        실손의료보험 외에 겹쳐 있는 보장
      </h3>
      <p className="mt-2 text-sm leading-6 text-zinc-600">
        운전자·배상책임처럼 실제 발생한 손해를 기준으로 보상하는 담보 중,
        실손의료보험이 아닌 중복 보장을 확인해요.
      </p>

      {duplicateGroups.length > 0 ? (
        <div className="mt-4 space-y-3">
          <Alert
            variant="warning"
            role="note"
            className="rounded-2xl border-amber-200 px-4 py-3 text-sm leading-6 text-amber-800"
          >
            중복 확인된 비의료 실손형 담보 {duplicateGroups.length}건
          </Alert>
          <ul className="space-y-3">
            {duplicateGroups.map((group) => (
              <li
                key={`${group.domain}-${group.normalizedName}`}
                className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3"
              >
                <p className="text-sm font-semibold text-zinc-900">
                  {group.displayName}
                </p>
                {group.explanation ? (
                  <p className="mt-1 text-xs leading-5 text-zinc-500">
                    {group.explanation}
                  </p>
                ) : null}
                <p className="mt-2 text-xs font-medium text-amber-700">
                  {group.contractCount}개 계약에서 확인됐어요.
                </p>
                <ul className="mt-2 space-y-1 text-xs leading-5 text-zinc-600">
                  {group.items.map((coverage) => (
                    <li
                      key={`${coverage.policy_id ?? "policy"}-${coverage.coverage_name}-${coverage.product_name}`}
                    >
                      {coverage.insurer} · {coverage.product_name} ·{" "}
                      {coverage.coverage_name}
                      {!group.explanation ? (
                        <span className="mt-0.5 block text-zinc-500">
                          {coverage.explanation}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      ) : nonMedicalCoverages.length > 0 ? (
        <Card
          variant="muted"
          className="mt-4 px-4 py-3 text-sm leading-6 text-zinc-600"
        >
          실손의료보험 외에 여러 계약에 함께 표시된 실손형 담보는 없어요.
        </Card>
      ) : (
        <Card
          variant="muted"
          className="mt-4 px-4 py-3 text-sm leading-6 text-zinc-600"
        >
          현재 자료에서 실손의료보험 외에 비교할 실손형 담보가 없어요.
        </Card>
      )}
    </article>
  );
}
