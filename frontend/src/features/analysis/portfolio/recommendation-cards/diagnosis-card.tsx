import { Badge } from "@/shared/components/ui/badge";

import type { EssentialCoverageItem } from "../api";
import { CoverageStatusBadge } from "../coverage-guide";
import {
  CORE_COVERAGE_DESCRIPTION,
  diagnosisDescription,
} from "./coverage-copy";
import type { DiagnosisKind } from "./coverage-copy";
import { CoverageGroupList } from "./coverage-group-list";
import { CoverageReference } from "./coverage-reference";
import { CoreCoverageSection } from "./core-coverage-section";

type DiagnosisCoverageItem = EssentialCoverageItem & { kind: DiagnosisKind };

export function recommendedDiagnosisItems(
  items: EssentialCoverageItem[],
): DiagnosisCoverageItem[] {
  return items.filter(
    (item): item is DiagnosisCoverageItem =>
      item.kind === "cancer" ||
      item.kind === "cerebrovascular" ||
      item.kind === "ischemic_heart",
  );
}

export function RecommendedDiagnosisCard({
  items,
  confirmedCount,
}: {
  items: DiagnosisCoverageItem[];
  confirmedCount: number;
}) {
  return (
    <CoreCoverageSection
      title="진단 보장"
      description={CORE_COVERAGE_DESCRIPTION.diagnosis}
      status={
        <Badge
          variant="neutral"
          className="h-auto rounded-full bg-white px-3 py-1 ring-1 ring-zinc-200"
        >
          {confirmedCount}/3 확인
        </Badge>
      }
    >
      <ul className="mt-5 grid gap-3 border-t border-zinc-200 pt-5 lg:grid-cols-3">
        {items.map((item) => (
          <RecommendedDiagnosisItem key={item.kind} item={item} />
        ))}
      </ul>
    </CoreCoverageSection>
  );
}

function RecommendedDiagnosisItem({ item }: { item: DiagnosisCoverageItem }) {
  return (
    <li className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-zinc-950">{item.label}</p>
          <p className="mt-1 text-xs leading-5 text-zinc-600">
            {diagnosisDescription(item.kind)}
          </p>
          {item.guidance_situation ? (
            <p className="mt-1 text-xs leading-5 text-zinc-600">
              {item.guidance_situation}
            </p>
          ) : null}
        </div>
        <CoverageStatusBadge status={item.status} />
      </div>

      <div className="mt-3">
        <CoverageReference item={item} compact showBasis={false} />
      </div>

      <CoverageGroupList
        groups={item.coverage_groups ?? []}
        fallbackNames={item.matched_coverage_names ?? []}
        emptyNotice="현재 업로드된 보험증권에서는 해당 보장이 확인되지 않아요"
      />
    </li>
  );
}
