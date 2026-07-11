import type { PortfolioSummary } from "./portfolio-api";

type Props = {
  status: "loading" | "error" | "success";
  summary?: PortfolioSummary;
  onRetry: () => void;
};

export function CoverageTotalTable({ status, summary, onRetry }: Props) {
  return (
    <section
      className="mt-8 overflow-hidden rounded-2xl border border-zinc-200 bg-white"
      aria-labelledby="coverage-total-title"
    >
      <div className="border-b border-zinc-100 px-5 py-5 sm:px-6">
        <h2
          id="coverage-total-title"
          className="text-xl font-semibold tracking-[-0.04em]"
        >
          보험금 합계
        </h2>
        <p className="mt-1 text-sm leading-6 text-zinc-500">
          증권에서 금액을 확인한 보장만 더했어요.
        </p>
      </div>
      {status === "loading" ? (
        <div role="status" className="space-y-3 px-6 py-7">
          <p className="text-sm text-zinc-500">
            보험금 합계를 불러오고 있어요.
          </p>
          <div className="h-10 animate-pulse rounded-lg bg-zinc-100" />
        </div>
      ) : status === "error" ? (
        <div className="px-6 py-7">
          <p className="text-sm text-zinc-600">
            보험금 합계를 불러오지 못했어요.
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-sm font-semibold text-blue-600"
          >
            다시 불러오기
          </button>
        </div>
      ) : summary?.totals.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-6 py-3 font-medium">보장</th>
                <th className="px-6 py-3 text-right font-medium">합계</th>
                <th className="px-6 py-3 text-right font-medium">
                  포함한 담보
                </th>
              </tr>
            </thead>
            {groupTotals(summary.totals).map(([majorCategory, totals]) => (
              <tbody
                key={majorCategory}
                className="divide-y divide-zinc-100 border-t border-zinc-200"
              >
                <tr className="bg-blue-50/50">
                  <th
                    colSpan={3}
                    className="px-6 py-3 text-xs font-semibold text-blue-700"
                  >
                    {majorCategory}
                  </th>
                </tr>
                {totals.map((total, index) => (
                  <tr key={`${total.normalizedName}-${index}`}>
                    <th className="px-6 py-4 font-medium text-zinc-800">
                      <details>
                        <summary className="cursor-pointer marker:text-zinc-400">
                          {total.category}
                        </summary>
                        <ul className="mt-3 space-y-1.5 text-xs font-normal text-zinc-500">
                          {total.composition.map((source, sourceIndex) => (
                            <li
                              key={`${source.policy_id ?? "policy"}-${sourceIndex}`}
                            >
                              {source.insurer ?? "보험사 확인 필요"} ·{" "}
                              {source.coverage_name} · {source.original_amount}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </th>
                    <td className="px-6 py-4 text-right font-semibold text-blue-600">
                      {formatWon(total.totalAmount)}
                    </td>
                    <td className="px-6 py-4 text-right text-zinc-500">
                      {total.coverageCount}개
                    </td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      ) : (
        <p className="px-6 py-8 text-sm text-zinc-500">
          합계에 포함할 수 있는 보장금액을 찾지 못했어요.
        </p>
      )}
      {status === "success" && summary?.indemnity_coverages.length ? (
        <div className="border-t border-zinc-100 px-6 py-5">
          <h3 className="text-sm font-semibold">실손형 담보</h3>
          <ul className="mt-2 space-y-1 text-sm text-zinc-600">
            {summary.indemnity_coverages.map((coverage, index) => (
              <li key={`${coverage.policy_id ?? "policy"}-${index}`}>
                {coverage.insurer ?? "보험사 확인 필요"} ·{" "}
                {coverage.coverage_name}
                {coverage.cross_insurer_duplicate ? " · 중복 확인 필요" : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {status === "success" && summary?.excluded_coverages.length ? (
        <details className="border-t border-zinc-100 px-6 py-5">
          <summary className="cursor-pointer text-sm font-semibold">
            확인이 필요한 담보 {summary.excluded_coverages.length}개
          </summary>
          <ul className="mt-3 space-y-2 text-sm text-zinc-600">
            {summary.excluded_coverages.map((coverage, index) => (
              <li key={`${coverage.policy_id ?? "policy"}-${index}`}>
                {coverage.coverage_name} · {coverage.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function formatWon(amount: number) {
  return `${amount.toLocaleString("ko-KR")}원`;
}

const MAJOR_CATEGORY_ORDER = [
  "진단비",
  "수술비",
  "치료비",
  "입원",
  "통원",
  "후유장해",
  "사망",
  "간병",
  "기타",
];

function groupTotals(totals: PortfolioSummary["totals"]) {
  const groups = new Map<string, typeof totals>();
  for (const total of totals) {
    const group = groups.get(total.majorCategory) ?? [];
    group.push(total);
    groups.set(total.majorCategory, group);
  }
  return [...groups.entries()].sort(
    ([left], [right]) =>
      MAJOR_CATEGORY_ORDER.indexOf(left) - MAJOR_CATEGORY_ORDER.indexOf(right),
  );
}
