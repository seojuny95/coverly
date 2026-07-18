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
  },
  needs_review: {
    label: "추가 확인",
    className: "bg-amber-50 text-amber-800",
  },
  not_found: {
    label: "현재 자료에서 미확인",
    className: "bg-zinc-100 text-zinc-600",
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
