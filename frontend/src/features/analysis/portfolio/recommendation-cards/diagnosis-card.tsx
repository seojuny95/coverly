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

// Kept as a <section> (not the Card primitive) for consistency with the
// sibling death-benefit and medical-indemnity cards in this group.
export function RecommendedDiagnosisCard({
  items,
  confirmedCount,
}: {
  items: DiagnosisCoverageItem[];
  confirmedCount: number;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h4 className="text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            진단 보장
          </h4>
          <p className="mt-2 text-sm leading-6 text-zinc-600">
            {CORE_COVERAGE_DESCRIPTION.diagnosis}
          </p>
        </div>
        <Badge
          variant="neutral"
          className="h-auto rounded-full bg-white px-3 py-1 ring-1 ring-zinc-200"
        >
          {confirmedCount}/3 확인
        </Badge>
      </div>

      <ul className="mt-5 grid gap-3 border-t border-zinc-200 pt-5 lg:grid-cols-3">
        {items.map((item) => (
          <RecommendedDiagnosisItem key={item.kind} item={item} />
        ))}
      </ul>
    </section>
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
