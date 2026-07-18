import type { VariantProps } from "class-variance-authority";

import { Badge, type badgeVariants } from "@/shared/components/ui/badge";

import type {
  EssentialCoverageItem,
  ReferenceSource,
  SourceReliability,
} from "./api";
import { safeHref } from "./safe-href";

type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

export const STATUS_COPY = {
  well_prepared: {
    label: "가입 확인",
    variant: "success" satisfies BadgeVariant,
  },
  needs_review: {
    label: "추가 확인",
    variant: "warning" satisfies BadgeVariant,
  },
  not_found: {
    label: "현재 자료에서 미확인",
    variant: "neutral" satisfies BadgeVariant,
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
    <Badge
      variant={STATUS_COPY[status].variant}
      className="h-auto px-3 py-1 text-xs font-medium"
    >
      {label ?? STATUS_COPY[status].label}
    </Badge>
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

  // Links keep a plain <a> (not Badge asChild) so hover styling stays
  // exactly as before; Badge's [a]:hover variants would otherwise leak in.
  const anchorClassName =
    "rounded-full border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] font-medium text-zinc-600";

  return (
    <div className={`mt-3 flex flex-wrap gap-1.5 ${className}`}>
      {sources.map((source) => {
        const href = safeHref(source.url);
        const label = sourceTypeLabel(source.reliability);

        return href ? (
          <a
            key={`${source.label}-${source.url}`}
            href={href}
            target="_blank"
            rel="noreferrer"
            className={anchorClassName}
            title={source.caveat}
          >
            {label}: {source.label}
          </a>
        ) : (
          <Badge
            key={`${source.label}-${source.url}`}
            variant="outline"
            className="h-auto rounded-full border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] font-medium text-zinc-600"
            title={source.caveat}
          >
            {label}: {source.label}
          </Badge>
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
