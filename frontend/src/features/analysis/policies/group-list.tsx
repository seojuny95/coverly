import { POLICY_CLASSIFICATIONS } from "@/shared/api/generated-runtime";
import { CollapseRegion } from "@/shared/components/disclosure";

import { POLICY_CLASSIFICATION_DESCRIPTIONS } from "./classification";
import { InsurerLogo, InsuranceDetail, TagBadge } from "./detail";
import type { AnalyzedInsurance } from "../session/store";

export function PolicyGroupList({
  groupedDocuments,
  isExpanded,
  onToggle,
}: {
  groupedDocuments: Record<string, AnalyzedInsurance[]>;
  isExpanded: (id: string) => boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="mt-8 space-y-5">
      {POLICY_CLASSIFICATIONS.map((classification) => {
        const documents = groupedDocuments[classification] ?? [];
        if (documents.length === 0) return null;

        return (
          <section
            key={classification}
            className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
          >
            <div className="border-b border-zinc-100 bg-zinc-50/60 px-5 py-4">
              <h2 className="text-lg font-semibold tracking-[-0.03em]">
                {classification}
              </h2>
              <p className="mt-1 text-sm leading-6 text-zinc-500">
                {POLICY_CLASSIFICATION_DESCRIPTIONS[classification]}
              </p>
              <p className="mt-1 text-xs font-medium text-zinc-400">
                보험 {documents.length}개
              </p>
            </div>

            <ul className="divide-y divide-zinc-100">
              {documents.map((document) => {
                const expanded = isExpanded(document.id);
                const basicInfo = document.result.기본정보;

                return (
                  <li key={document.id}>
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => onToggle(document.id)}
                      className="flex w-full flex-col gap-4 px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-inset sm:flex-row sm:items-center sm:justify-between"
                    >
                      <span className="flex min-w-0 items-start gap-3">
                        <InsurerLogo
                          insurerName={basicInfo?.보험사 ?? undefined}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex min-w-0 items-center gap-2">
                            <span className="truncate text-base font-semibold text-zinc-950">
                              {basicInfo?.상품명 ?? document.fileName}
                            </span>
                            {basicInfo?.상품태그?.length ? (
                              <span className="flex shrink-0 flex-wrap gap-1.5">
                                {basicInfo.상품태그.map((tag) => (
                                  <TagBadge key={tag} tag={tag} />
                                ))}
                              </span>
                            ) : null}
                          </span>
                          <span className="mt-1 block truncate text-sm text-zinc-500">
                            {document.fileName}
                          </span>
                        </span>
                      </span>
                      <span className="inline-flex shrink-0 items-center rounded-lg border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                        {expanded ? "접기" : "자세히 보기"}
                      </span>
                    </button>

                    <CollapseRegion expanded={expanded}>
                      <InsuranceDetail
                        insuranceDocument={document}
                        isExpanded={expanded}
                      />
                    </CollapseRegion>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
