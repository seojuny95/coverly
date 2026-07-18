import { Card } from "@/shared/components/ui/card";

import type { EssentialCoverageItem } from "../api";
import { ReferenceSourceList } from "../coverage-guide";
import { formatKoreanWon } from "../money-format";

export function CoverageReference({
  item,
  isRefreshing = false,
}: {
  item: EssentialCoverageItem | undefined;
  isRefreshing?: boolean;
}) {
  if (isRefreshing) {
    return (
      <div
        role="status"
        aria-label="참고 금액을 다시 확인하고 있어요"
        aria-busy="true"
        aria-live="polite"
        className="h-28 animate-pulse rounded-2xl bg-zinc-100"
      />
    );
  }

  if (!item) {
    return (
      <Card variant="dashed" className="px-4 py-3 text-sm text-zinc-500">
        확인 결과를 불러오지 못했어요.
      </Card>
    );
  }

  const referenceAmount =
    item.reference_amount_label ??
    formatReferenceAmount(item.reference_min_amount, item.reference_max_amount);

  return (
    <Card className="border-transparent p-4 ring-1 ring-zinc-200">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold text-zinc-500">현재 가입금액</p>
          <p className="mt-1 text-lg font-semibold text-zinc-950">
            {item.confirmed_amount == null
              ? "미확인"
              : formatKoreanWon(item.confirmed_amount)}
          </p>
        </div>
        {referenceAmount ? (
          <div>
            <p className="text-xs font-semibold text-zinc-500">참고 금액</p>
            <p className="mt-1 text-sm font-medium text-zinc-700">
              {referenceAmount}
            </p>
          </div>
        ) : null}
      </div>
      {item.reference_basis ? (
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          {item.reference_basis}
        </p>
      ) : null}
      {item.guidance_reason && item.guidance_reason !== item.reference_basis ? (
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          {item.guidance_reason}
        </p>
      ) : null}
      <ReferenceSourceList sources={item.reference_sources ?? []} />
    </Card>
  );
}

function formatReferenceAmount(
  minAmount: number | null | undefined,
  maxAmount: number | null | undefined,
) {
  if (minAmount == null || maxAmount == null) return null;
  if (minAmount === maxAmount) return formatKoreanWon(minAmount);
  return `${formatKoreanWon(minAmount)} ~ ${formatKoreanWon(maxAmount)}`;
}
