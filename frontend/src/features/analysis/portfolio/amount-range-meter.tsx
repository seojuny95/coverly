import type { CSSProperties } from "react";

import { cn } from "@/shared/lib/utils";

type AmountRangeMeterProps = {
  current: number | null | undefined;
  referenceMin: number | null | undefined;
  referenceMax: number | null | undefined;
  currentLabel?: string;
  referenceLabel?: string;
  formatAmount: (amount: number) => string;
  tone?: "light" | "dark";
};

export function AmountRangeMeter({
  current,
  referenceMin,
  referenceMax,
  currentLabel = "현재",
  referenceLabel = "권장",
  formatAmount,
  tone = "light",
}: AmountRangeMeterProps) {
  if (referenceMin == null || referenceMax == null) return null;

  const normalizedMin = Math.min(referenceMin, referenceMax);
  const normalizedMax = Math.max(referenceMin, referenceMax);
  const currentAmount =
    typeof current === "number" && Number.isFinite(current) ? current : null;
  const scaleMax = niceScaleMax(Math.max(normalizedMax, currentAmount ?? 0));
  const currentEnd = amountPercent(currentAmount ?? 0, scaleMax);
  const referenceMinPosition = amountPercent(normalizedMin, scaleMax);
  const referenceMaxPosition = amountPercent(normalizedMax, scaleMax);
  const referenceText =
    normalizedMin === normalizedMax
      ? formatAmount(normalizedMin)
      : `${formatAmount(normalizedMin)} ~ ${formatAmount(normalizedMax)}`;
  const currentText =
    currentAmount == null ? "미확인" : formatAmount(currentAmount);
  const currentPositionStyle = {
    "--amount-range-position": `${currentEnd}%`,
  } as CSSProperties;

  return (
    <div
      role="group"
      aria-label={`${currentLabel} ${currentText}, ${referenceLabel} ${referenceText}`}
      className="mt-4"
    >
      <div
        className={cn(
          "mb-1 flex items-center justify-between text-[11px] leading-4",
          tone === "dark" ? "text-zinc-300" : "text-zinc-500",
        )}
      >
        <span>{formatAmount(0)}</span>
        <span>{formatAmount(scaleMax)}</span>
      </div>
      <div
        className={cn(
          "relative h-12",
          tone === "dark" ? "text-blue-100" : "text-blue-700",
        )}
      >
        <div className="absolute top-9 h-2 w-full">
          <div
            className={cn(
              "h-full w-full rounded-full",
              tone === "dark" ? "bg-white/15" : "bg-zinc-100",
            )}
          />
          <span
            className={cn(
              // amount-range-fill carries the final width, so the bar still
              // reads correctly when reduced-motion drops the animation.
              "amount-range-fill animate-amount-range-fill absolute inset-y-0 left-0 rounded-full",
              tone === "dark" ? "bg-white" : "bg-blue-600",
            )}
            style={currentPositionStyle}
            role="progressbar"
            aria-label={`${currentLabel} 금액`}
            aria-valuemin={0}
            aria-valuemax={scaleMax}
            aria-valuenow={currentAmount ?? 0}
            aria-valuetext={currentText}
          >
            <span
              className={cn(
                "absolute top-1/2 right-0 size-3 translate-x-1/2 -translate-y-1/2 rounded-full ring-2",
                tone === "dark"
                  ? "bg-white ring-blue-950"
                  : "bg-blue-600 ring-white",
              )}
            />
          </span>
        </div>
        <ReferenceMarker
          label={referenceLabel}
          position={referenceMinPosition}
          tone={tone}
        />
        <ReferenceMarker
          label={referenceLabel}
          position={referenceMaxPosition}
          tone={tone}
        />
      </div>

      <div
        className={cn(
          "mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[11px] leading-4",
          tone === "dark" ? "text-zinc-300" : "text-zinc-500",
        )}
      >
        <span>
          {currentLabel}{" "}
          <strong
            className={cn(
              "font-semibold",
              tone === "dark" ? "text-white" : "text-zinc-800",
            )}
          >
            {currentText}
          </strong>
        </span>
        <span>
          {referenceLabel}{" "}
          <strong
            className={cn(
              "font-semibold",
              tone === "dark" ? "text-blue-100" : "text-blue-700",
            )}
          >
            {referenceText}
          </strong>
        </span>
      </div>
    </div>
  );
}

function ReferenceMarker({
  label,
  position,
  tone,
}: {
  label: string;
  position: number;
  tone: "light" | "dark";
}) {
  return (
    <>
      <span
        className={cn(
          "absolute top-3 text-[10px] leading-none font-semibold whitespace-nowrap",
          markerLabelClassName(position),
        )}
        style={markerStyle(position)}
        aria-hidden="true"
      >
        {label}
      </span>
      <span
        data-slot="amount-range-reference-arrow"
        className={cn(
          "absolute top-7 size-0 border-x-[5px] border-t-[7px] border-x-transparent",
          "-translate-x-1/2",
          tone === "dark" ? "border-t-blue-100" : "border-t-blue-700",
        )}
        style={{ left: `${position}%` }}
        aria-hidden="true"
      />
    </>
  );
}

function markerStyle(position: number): CSSProperties {
  if (position <= 8) return { left: 0 };
  if (position >= 92) return { right: 0 };
  return { left: `${position}%` };
}

function markerLabelClassName(position: number) {
  if (position <= 8) return "left-0 text-left";
  if (position >= 92) return "right-0 text-right";
  return "-translate-x-1/2 text-center";
}

function amountPercent(amount: number, scaleMax: number) {
  return Math.min(Math.max((amount / scaleMax) * 100, 0), 100);
}

function niceScaleMax(amount: number) {
  if (!Number.isFinite(amount) || amount <= 0) return 1;

  const target = amount * 1.2;
  const magnitude = 10 ** Math.floor(Math.log10(target));
  const normalized = target / magnitude;
  const niceNormalized =
    normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;

  return niceNormalized * magnitude;
}
