"use client";

import { CollapseRegion, useDisclosure } from "@/shared/components/disclosure";
import { Card } from "@/shared/components/ui/card";

import {
  type ActualLossCoverageGroup,
  actualLossCoverageDescription,
  duplicateActualLossCoverageGroups,
} from "../actual-loss-coverage-groups";
import type { EssentialCoverageItem, PortfolioSummary } from "../api";
import { CoverageStatusBadge, ReferenceSourceList } from "../coverage-guide";
import { CORE_COVERAGE_DESCRIPTION } from "./coverage-copy";
import { CoverageNamesNotice } from "./coverage-group-list";
import { CoreCoverageSection } from "./core-coverage-section";

export function RecommendedMedicalIndemnityCard({
  actualLossCoverages,
  item,
}: {
  actualLossCoverages: PortfolioSummary["actual_loss_coverages"];
  item: EssentialCoverageItem | undefined;
}) {
  const medicalIndemnityCoverages = actualLossCoverages.filter(
    (coverage) => coverage.is_medical_indemnity,
  );
  const duplicateGroups = duplicateActualLossCoverageGroups(
    medicalIndemnityCoverages,
  );

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
            {medicalIndemnityHeadline(item, duplicateGroups)}
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">
            {duplicateGroups.length > 0
              ? "같은 실손의료비가 여러 계약에서 확인됐어요. 아래에서 겹친 담보와 계약을 확인해보세요."
              : (item?.detail ??
                "현재 자료에서 가입 여부를 확인하지 못했어요.")}
          </p>
          <ReferenceSourceList sources={item?.reference_sources ?? []} />
        </Card>
      </div>

      {duplicateGroups.length > 0 ? (
        <MedicalIndemnityDuplicateList groups={duplicateGroups} />
      ) : (
        <CoverageNamesNotice names={item?.matched_coverage_names ?? []} />
      )}
    </CoreCoverageSection>
  );
}

function medicalIndemnityHeadline(
  item: EssentialCoverageItem | undefined,
  duplicateGroups: ReturnType<typeof duplicateActualLossCoverageGroups>,
) {
  if (duplicateGroups.length > 0) {
    const coverageCount = duplicateGroups.reduce(
      (count, group) => count + group.items.length,
      0,
    );

    return `중복된 실손의료비 ${duplicateGroups.length}종 · 담보 내역 ${coverageCount}건`;
  }
  if (!item || item.status === "not_found") {
    return "가입 여부 미확인";
  }
  if (item.status === "needs_review") {
    return `${item.coverage_count}건 확인`;
  }
  return "가입 확인";
}

function MedicalIndemnityDuplicateList({
  groups,
}: {
  groups: ReturnType<typeof duplicateActualLossCoverageGroups>;
}) {
  return (
    <ul className="mt-4 space-y-3">
      {groups.map((group) => (
        <MedicalIndemnityDuplicateItem
          key={`${group.domain}-${group.normalizedName}`}
          group={group}
        />
      ))}
    </ul>
  );
}

function MedicalIndemnityDuplicateItem({
  group,
}: {
  group: ActualLossCoverageGroup;
}) {
  const { expanded, toggle, panelId } = useDisclosure();

  return (
    <li>
      <Card className="overflow-hidden border-transparent ring-1 ring-zinc-200">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={toggle}
          className="flex w-full cursor-pointer items-start justify-between gap-4 px-4 py-3 text-left transition-colors duration-150 hover:bg-zinc-50 focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-none focus-visible:ring-inset motion-reduce:transition-none"
        >
          <span>
            <span className="block text-sm font-semibold text-zinc-900">
              {group.displayName}
            </span>
            <span className="mt-1 block text-xs leading-5 text-zinc-500">
              {actualLossCoverageDescription(group.displayName)}
            </span>
            <span className="mt-2 block text-xs font-medium text-amber-700">
              {group.items.length}개 계약에서 확인됐어요.
            </span>
          </span>
          <span
            aria-hidden="true"
            className={`mt-0.5 shrink-0 text-zinc-400 transition-transform duration-200 ease-out motion-reduce:transition-none ${
              expanded ? "rotate-90" : ""
            }`}
          >
            ›
          </span>
        </button>

        <CollapseRegion expanded={expanded} id={panelId}>
          <ul className="space-y-1 border-t border-zinc-100 px-4 py-3 text-xs leading-5 text-zinc-600">
            {group.items.map((coverage) => (
              <li
                key={`${coverage.policy_id ?? "policy"}-${coverage.coverage_name}-${coverage.product_name}`}
              >
                {coverage.insurer} · {coverage.product_name} ·{" "}
                {coverage.coverage_name}
              </li>
            ))}
          </ul>
        </CollapseRegion>
      </Card>
    </li>
  );
}
