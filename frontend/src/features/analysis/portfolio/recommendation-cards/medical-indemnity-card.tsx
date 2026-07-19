import { Card } from "@/shared/components/ui/card";

import type { EssentialCoverageItem } from "../api";
import { CoverageStatusBadge, ReferenceSourceList } from "../coverage-guide";
import { CORE_COVERAGE_DESCRIPTION } from "./coverage-copy";
import { CoverageNamesNotice } from "./coverage-group-list";
import { CoreCoverageSection } from "./core-coverage-section";

export function RecommendedMedicalIndemnityCard({
  item,
}: {
  item: EssentialCoverageItem | undefined;
}) {
  return (
    <CoreCoverageSection
      title={item?.label ?? "실손의료 보장"}
      description={CORE_COVERAGE_DESCRIPTION.medicalIndemnity}
      status={<CoverageStatusBadge status={item?.status ?? "not_found"} />}
    >
      <div className="mt-5 border-t border-zinc-200 pt-5">
        <Card className="border-transparent p-4 ring-1 ring-zinc-200">
          <p className="text-xs font-semibold text-zinc-500">현재 확인 결과</p>
          <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-zinc-950">
            {medicalIndemnityHeadline(item)}
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">
            {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
          </p>
          <ReferenceSourceList sources={item?.reference_sources ?? []} />
        </Card>
      </div>

      <CoverageNamesNotice names={item?.matched_coverage_names ?? []} />
    </CoreCoverageSection>
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
