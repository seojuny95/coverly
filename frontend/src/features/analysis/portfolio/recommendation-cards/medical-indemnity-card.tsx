import { Card } from "@/shared/components/ui/card";

import type { EssentialCoverageItem } from "../api";
import { CoverageStatusBadge, ReferenceSourceList } from "../coverage-guide";
import { CoverageNamesNotice } from "./coverage-group-list";

// Kept as a <section> (not the Card primitive) for consistency with the
// sibling death-benefit and diagnosis cards in this group.
export function RecommendedMedicalIndemnityCard({
  item,
}: {
  item: EssentialCoverageItem | undefined;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
            실제 의료비
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {item?.label ?? "실손의료 보장"}
          </h4>
        </div>
        <CoverageStatusBadge status={item?.status ?? "not_found"} />
      </div>

      <div
        className={`mt-5 grid gap-4 border-t border-zinc-200 pt-5 ${item?.reference_basis ? "lg:grid-cols-2" : ""}`}
      >
        <Card className="border-transparent p-4 ring-1 ring-zinc-200">
          <p className="text-xs font-semibold text-zinc-500">현재 확인 결과</p>
          <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-zinc-950">
            {medicalIndemnityHeadline(item)}
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">
            {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
          </p>
        </Card>

        {item?.reference_basis ? (
          <Card variant="dashed" className="px-4 py-3">
            <p className="text-xs font-semibold text-zinc-500">확인 기준</p>
            <p className="mt-1 text-sm leading-6 text-zinc-700">
              {item.reference_basis}
            </p>
            <ReferenceSourceList sources={item.reference_sources ?? []} />
          </Card>
        ) : null}
      </div>

      <CoverageNamesNotice names={item?.matched_coverage_names ?? []} />
    </section>
  );
}

function medicalIndemnityHeadline(item: EssentialCoverageItem | undefined) {
  if (!item || item.status === "not_found") {
    return "가입 여부 미확인";
  }
  if (item.status === "needs_review") {
    return `${item.coverage_count}건 확인`;
  }
  return "가입 확인";
}
