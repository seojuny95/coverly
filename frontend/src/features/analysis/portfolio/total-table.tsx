import { Badge } from "@/shared/components/ui/badge";
import { RetryButton } from "@/shared/components/retry-button";
import { Skeleton } from "@/shared/components/ui/skeleton";

import { CoverageSummaryTable } from "./summary-table";
import type { PortfolioSummary } from "./api";

type Props = {
  status: "loading" | "error" | "success";
  summary?: PortfolioSummary;
  onRetry: () => void;
  isRetrying?: boolean;
  retryFailed?: boolean;
};

export function CoverageTotalTable({
  status,
  summary,
  onRetry,
  isRetrying = false,
  retryFailed = false,
}: Props) {
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
          확인된 합산 금액과 실손 보장을 함께 보여드려요.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs leading-5 text-zinc-500">
          <CoverageBasisLegend term="합산" variant="info">
            더할 수 있는 정액 보장
          </CoverageBasisLegend>
          <CoverageBasisLegend term="실손 보장" variant="success">
            실제 손해 기준 보장
          </CoverageBasisLegend>
          <CoverageBasisLegend term="개별 확인" variant="neutral">
            조건 확인이 필요한 보장
          </CoverageBasisLegend>
        </div>
      </div>

      {status === "loading" ? (
        <CoverageSummaryLoading />
      ) : status === "error" ? (
        <CoverageSummaryError
          onRetry={onRetry}
          isRetrying={isRetrying}
          retryFailed={retryFailed}
        />
      ) : (
        <div className="animate-enter">
          {summary && hasCoverages ? (
            <CoverageSummaryTable summary={summary} />
          ) : (
            <p className="px-6 py-8 text-sm text-zinc-500">
              표시할 보장금액을 찾지 못했어요.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function CoverageBasisLegend({
  children,
  term,
  variant,
}: {
  children: string;
  term: string;
  variant: "info" | "success" | "neutral";
}) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <Badge
        variant={variant}
        className="h-auto rounded-full px-2 py-0.5 text-xs font-semibold"
      >
        {term}
      </Badge>
      <span className="min-w-0">{children}</span>
    </span>
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
      <div className="mt-5 space-y-3" aria-hidden="true">
        <div className="grid grid-cols-[1fr_7rem_7rem] gap-4 border-b border-zinc-100 pb-3">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3" />
          <Skeleton className="h-3" />
        </div>
        {[0, 1, 2].map((row) => (
          <div
            key={row}
            className="grid grid-cols-[1fr_7rem_7rem] items-center gap-4 py-2"
          >
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-64 max-w-full" />
            </div>
            <Skeleton className="h-4 bg-blue-100" />
            <Skeleton className="h-6 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

function CoverageSummaryError({
  onRetry,
  isRetrying,
  retryFailed,
}: {
  onRetry: () => void;
  isRetrying: boolean;
  retryFailed: boolean;
}) {
  return (
    <div className="px-6 py-7">
      <p
        role={retryFailed ? "alert" : undefined}
        className="text-sm text-zinc-600"
      >
        {retryFailed
          ? "보장금 합계를 다시 불러오지 못했어요. 잠시 후 다시 시도해주세요."
          : "보장금 합계를 불러오지 못했어요."}
      </p>
      <RetryButton
        type="button"
        onClick={onRetry}
        variant="link"
        className="mt-3 min-h-0 px-0 py-0 text-sm font-semibold text-blue-600"
        isPending={isRetrying}
        label="다시 불러오기"
        pendingLabel="다시 불러오는 중…"
      />
    </div>
  );
}
