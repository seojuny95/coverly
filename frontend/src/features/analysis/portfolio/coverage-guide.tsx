import type { CSSProperties, ReactNode } from "react";

import { formatKoreanWon } from "./money-format";
import type {
  EssentialCoverageItem,
  ReferenceSource,
  SourceReliability,
} from "./api";
import { safeHref } from "./safe-href";

export const STATUS_COPY = {
  well_prepared: {
    label: "가입 확인",
    className: "bg-emerald-50 text-emerald-700",
    dotClassName: "bg-emerald-500",
  },
  needs_review: {
    label: "중복 가능성 확인",
    className: "bg-amber-50 text-amber-800",
    dotClassName: "bg-amber-500",
  },
  not_found: {
    label: "현재 자료에서 미확인",
    className: "bg-zinc-100 text-zinc-600",
    dotClassName: "bg-zinc-400",
  },
} as const;

export function CoverageStatusBadge({
  status,
  label,
}: {
  status: EssentialCoverageItem["status"];
  label?: string;
}) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_COPY[status].className}`}
    >
      {label ?? STATUS_COPY[status].label}
    </span>
  );
}

export function CoverageAmountMeter({
  item,
  rangeLabel,
  fallbackNote,
  isRefreshing = false,
}: {
  item: EssentialCoverageItem | undefined;
  rangeLabel: string;
  fallbackNote: string;
  isRefreshing?: boolean;
}) {
  const currentAmount = item?.confirmed_amount ?? null;
  const minAmount = item?.reference_min_amount ?? null;
  const maxAmount = item?.reference_max_amount ?? null;
  const basis = item?.reference_basis ?? fallbackNote;
  const sources = item?.reference_sources ?? [];
  const amountLabel = item?.reference_amount_label ?? null;

  if (minAmount == null || maxAmount == null) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold text-zinc-500">{rangeLabel}</p>
        <p className="mt-1 text-sm leading-6 text-zinc-700">{basis}</p>
        <ReferenceSourceList sources={sources} />
      </div>
    );
  }

  if (isRefreshing) {
    return <CoverageAmountMeterSkeleton />;
  }

  const scaleMax = Math.max(currentAmount ?? 0, maxAmount) * 1.2 || maxAmount;
  const minPosition = progressPosition(minAmount, scaleMax);
  const maxPosition = progressPosition(maxAmount, scaleMax);
  const currentPosition = progressPosition(currentAmount ?? 0, scaleMax);
  const isRange = minAmount !== maxAmount;
  const style = {
    "--premium-position": `${currentPosition}%`,
  } as CSSProperties;

  return (
    <div className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-zinc-500">현재 가입금액</p>
          <p className="mt-1 text-lg font-semibold text-zinc-950">
            {currentAmount ? formatKoreanWon(currentAmount) : "미확인"}
          </p>
        </div>
        <div className="text-right text-xs leading-5 text-zinc-500">
          <p>{rangeLabel}</p>
          <p className="font-medium text-zinc-700">
            {amountLabel ??
              `${formatKoreanWon(minAmount)}${
                minAmount !== maxAmount
                  ? ` ~ ${formatKoreanWon(maxAmount)}`
                  : ""
              }`}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="relative h-24" style={style}>
          <div className="absolute inset-x-0 top-10 h-2 rounded-full bg-zinc-100" />
          <div className="premium-position-fill absolute top-10 left-0 z-10 h-2 rounded-full bg-blue-600" />
          <div
            className="absolute top-10 z-20 h-2 rounded-full bg-emerald-300/60 ring-2 ring-white/80"
            style={{
              left: `${minPosition}%`,
              width: `${Math.max(maxPosition - minPosition, 4)}%`,
            }}
          />
          {isRange ? (
            <>
              <RangeArrow left={minPosition} label="권장" tone="emerald" />
              <RangeArrow left={maxPosition} label="권장" tone="emerald" />
            </>
          ) : (
            <RangeArrow left={minPosition} label="권장" tone="emerald" />
          )}
          <span
            aria-hidden="true"
            className="absolute top-9 z-40 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white bg-blue-600 shadow-sm"
            style={{ left: `${currentPosition}%` }}
          />
          <PositionLabel left={currentPosition}>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap text-blue-700 ring-1 ring-blue-100/80">
              {currentAmount ? formatKoreanWon(currentAmount) : "미확인"}
            </span>
          </PositionLabel>
          <div className="absolute inset-x-0 top-20 flex justify-between text-[11px] text-zinc-400">
            <span>0원</span>
            <span>{formatKoreanWon(Math.round(scaleMax))}</span>
          </div>
        </div>
      </div>

      <p className="mt-3 text-xs leading-5 text-zinc-500">{basis}</p>
      <ReferenceSourceList sources={sources} />
    </div>
  );
}

function CoverageAmountMeterSkeleton() {
  return (
    <div
      className="rounded-2xl bg-white p-4 ring-1 ring-blue-200"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-zinc-500">현재 가입금액</p>
          <div className="mt-2 h-6 w-28 animate-pulse rounded bg-zinc-200" />
        </div>
        <div className="text-right">
          <p className="rounded-full bg-blue-50 px-2.5 py-1 text-sm font-medium text-blue-700">
            안내금액 계산 중
          </p>
          <div className="mt-2 ml-auto h-4 w-24 animate-pulse rounded bg-zinc-200" />
        </div>
      </div>

      <div className="mt-5 h-24 rounded-xl bg-zinc-50 p-4">
        <div className="mt-8 h-2 animate-pulse rounded-full bg-zinc-200" />
        <div className="mt-5 flex justify-between">
          <div className="h-3 w-10 animate-pulse rounded bg-zinc-200" />
          <div className="h-3 w-16 animate-pulse rounded bg-zinc-200" />
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <div className="h-3 w-full animate-pulse rounded bg-zinc-200" />
        <div className="h-3 w-3/4 animate-pulse rounded bg-zinc-200" />
      </div>
    </div>
  );
}

export function ReferenceSourceList({
  sources,
  className = "",
}: {
  sources: ReferenceSource[];
  className?: string;
}) {
  if (sources.length === 0) return null;

  return (
    <div className={`mt-3 flex flex-wrap gap-1.5 ${className}`}>
      {sources.map((source) => {
        const href = safeHref(source.url);
        const label = sourceTypeLabel(source.reliability);
        const className =
          "rounded-full border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] font-medium text-zinc-600";

        return href ? (
          <a
            key={`${source.label}-${source.url}`}
            href={href}
            target="_blank"
            rel="noreferrer"
            className={className}
            title={source.caveat}
          >
            {label}: {source.label}
          </a>
        ) : (
          <span
            key={`${source.label}-${source.url}`}
            className={className}
            title={source.caveat}
          >
            {label}: {source.label}
          </span>
        );
      })}
    </div>
  );
}

export function sourceTypeLabel(reliability: SourceReliability) {
  switch (reliability) {
    case "official":
      return "공식 출처";
    case "public_research":
      return "공공 연구 출처";
    case "industry":
      return "협회·공시 출처";
    case "large_private_analysis":
      return "민간 분석 출처";
    case "private_guidance":
      return "아티클·블로그 출처";
  }
}

export function RangeArrow({
  left,
  label,
  tone,
}: {
  left: number;
  label: string;
  tone: "emerald" | "white";
}) {
  const labelClassName =
    tone === "white"
      ? "bg-white/10 text-zinc-100 ring-1 ring-white/10"
      : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
  const arrowClassName =
    tone === "white" ? "text-zinc-200" : "text-emerald-500";

  return (
    <div
      className="absolute top-0 z-50 flex h-10 -translate-x-1/2 flex-col items-center justify-end"
      style={{ left: `${left}%` }}
    >
      <span
        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${labelClassName}`}
      >
        {label}
      </span>
      <span
        aria-hidden="true"
        className={`-mb-px h-0 w-0 border-x-[5px] border-t-[7px] border-x-transparent ${arrowClassName}`}
      />
    </div>
  );
}

export function PositionLabel({
  left,
  children,
}: {
  left: number;
  children: ReactNode;
}) {
  const alignmentClassName =
    left <= 5
      ? "translate-x-0"
      : left >= 95
        ? "-translate-x-full"
        : "-translate-x-1/2";

  return (
    <div
      className={`absolute top-14 z-40 ${alignmentClassName}`}
      style={{ left: `${left}%` }}
    >
      {children}
    </div>
  );
}

export function progressPosition(amount: number, maxAmount: number) {
  if (!Number.isFinite(amount) || maxAmount <= 0) return 0;
  return Math.min((amount / maxAmount) * 100, 100);
}
