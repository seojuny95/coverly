import { CoverageSummaryTable } from "./summary-table";
import type { PortfolioSummary } from "./api";

type Props = {
  status: "loading" | "error" | "success";
  summary?: PortfolioSummary;
  onRetry: () => void;
};

export function CoverageTotalTable({ status, summary, onRetry }: Props) {
  const hasCoverages = summary
    ? summary.totals.length > 0 ||
      summary.actual_loss_coverages.some(
        (coverage) => !coverage.is_damage_policy,
      ) ||
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
          보장금 합계
        </h2>
        <p className="mt-1 text-sm leading-6 text-zinc-500">
          생명보험과 제3보험의 보장을 합산 기준에 따라 묶어서 보여드려요.
        </p>
        <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs leading-5">
          <LegendItem term="정액보상" termClassName="bg-blue-50 text-blue-700">
            약속된 보장금액은 보험별로 합산해 봐요
          </LegendItem>
          <LegendItem
            term="실손보장"
            termClassName="bg-emerald-50 text-emerald-700"
          >
            실제 발생한 손해를 보상하는 담보라 합산하지 않아요
          </LegendItem>
          <LegendItem
            term="개별 확인"
            termClassName="bg-zinc-100 text-zinc-600"
          >
            지급 방식을 확인 못 해 따로 봐요
          </LegendItem>
        </dl>
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

function LegendItem({
  term,
  termClassName,
  children,
}: {
  term: string;
  termClassName: string;
  children: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <dt
        className={`inline-flex shrink-0 rounded-full px-2 py-0.5 font-semibold ${termClassName}`}
      >
        {term}
      </dt>
      <dd className="text-zinc-500">{children}</dd>
    </div>
  );
}

function CoverageSummaryLoading() {
  return (
    <div
      role="status"
      aria-label="보장금 합계를 불러오고 있어요."
      className="px-6 py-5"
    >
      <p className="text-sm text-zinc-500">보장금 합계를 불러오고 있어요.</p>
      <div className="mt-5 animate-pulse space-y-3" aria-hidden="true">
        <div className="grid grid-cols-[1fr_7rem_7rem] gap-4 border-b border-zinc-100 pb-3">
          <div className="h-3 w-16 rounded bg-zinc-100" />
          <div className="h-3 rounded bg-zinc-100" />
          <div className="h-3 rounded bg-zinc-100" />
        </div>
        {[0, 1, 2].map((row) => (
          <div
            key={row}
            className="grid grid-cols-[1fr_7rem_7rem] items-center gap-4 py-2"
          >
            <div className="space-y-2">
              <div className="h-4 w-40 rounded bg-zinc-100" />
              <div className="h-3 w-64 max-w-full rounded bg-zinc-100" />
            </div>
            <div className="h-4 rounded bg-blue-100" />
            <div className="h-6 rounded-full bg-zinc-100" />
          </div>
        ))}
      </div>
    </div>
  );
}

function CoverageSummaryError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="px-6 py-7">
      <p className="text-sm text-zinc-600">보장금 합계를 불러오지 못했어요.</p>
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
