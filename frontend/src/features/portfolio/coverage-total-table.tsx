import { CoverageSummaryTable } from "./coverage-summary-table";
import type { PortfolioSummary } from "./portfolio-api";

type Props = {
  status: "loading" | "error" | "success";
  summary?: PortfolioSummary;
  onRetry: () => void;
};

export function CoverageTotalTable({ status, summary, onRetry }: Props) {
  const hasCoverages = summary
    ? summary.totals.length > 0 ||
      summary.indemnity_coverages.length > 0 ||
      summary.excluded_coverages.length > 0
    : false;

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
          같은 정액형 담보는 합산하고, 그 외 담보는 가입금액 그대로 보여드려요.
        </p>
      </div>

      {status === "loading" ? (
        <CoverageSummaryLoading />
      ) : status === "error" ? (
        <CoverageSummaryError onRetry={onRetry} />
      ) : summary && hasCoverages ? (
        <CoverageSummaryTable summary={summary} />
      ) : (
        <p className="px-6 py-8 text-sm text-zinc-500">
          표시할 보장금액을 찾지 못했어요.
        </p>
      )}
    </section>
  );
}

function CoverageSummaryLoading() {
  return (
    <div role="status" className="space-y-3 px-6 py-7">
      <p className="text-sm text-zinc-500">보험금 합계를 불러오고 있어요.</p>
      <div className="h-10 animate-pulse rounded-lg bg-zinc-100" />
    </div>
  );
}

function CoverageSummaryError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="px-6 py-7">
      <p className="text-sm text-zinc-600">보험금 합계를 불러오지 못했어요.</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 text-sm font-semibold text-blue-600"
      >
        다시 불러오기
      </button>
    </div>
  );
}
