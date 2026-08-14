import { cn } from "@/shared/lib/utils";

import type { DeathBenefitGuideInput, EssentialCoverageItem } from "../api";
import { CoverageStatusBadge } from "../coverage-guide";
import { CoverageGroupList } from "./coverage-group-list";
import { CORE_COVERAGE_DESCRIPTION } from "./coverage-copy";
import { CoverageReference } from "./coverage-reference";
import { CoreCoverageSection } from "./core-coverage-section";

export function RecommendedDeathBenefitCard({
  item,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isRefreshing,
}: {
  item: EssentialCoverageItem | undefined;
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isRefreshing: boolean;
}) {
  const selectedOption: keyof DeathBenefitGuideInput | "none" =
    deathBenefitContext.has_dependent_family
      ? "has_dependent_family"
      : deathBenefitContext.has_minor_children
        ? "has_minor_children"
        : deathBenefitContext.has_major_debt
          ? "has_major_debt"
          : "none";

  const selectDeathBenefitContext = (
    option: keyof DeathBenefitGuideInput | "none",
  ) => {
    onDeathBenefitContextChange({
      has_dependent_family: option === "has_dependent_family",
      has_minor_children: option === "has_minor_children",
      has_major_debt: option === "has_major_debt",
    });
  };

  return (
    <CoreCoverageSection
      title={item?.label ?? "확인 결과"}
      description={CORE_COVERAGE_DESCRIPTION.death}
      status={
        <CoverageStatusBadge
          status={item?.status ?? "not_found"}
          label={
            item?.kind === "death" && item.status === "needs_review"
              ? "점검 필요"
              : undefined
          }
        />
      }
    >
      <div className="mt-5 space-y-4 border-t border-zinc-200 pt-5">
        <fieldset className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
          <legend className="sr-only">나의 상황</legend>
          <p className="text-xs font-semibold text-zinc-500">나의 상황</p>
          <div className="mt-3 space-y-2">
            <DeathBenefitRadio
              checked={selectedOption === "none"}
              label="부양가족이나 큰 부채가 없어요"
              onChange={() => selectDeathBenefitContext("none")}
            />
            <DeathBenefitRadio
              checked={selectedOption === "has_dependent_family"}
              label="내 소득에 의존하는 가족이 있어요"
              onChange={() => selectDeathBenefitContext("has_dependent_family")}
            />
            <DeathBenefitRadio
              checked={selectedOption === "has_minor_children"}
              label="미성년 자녀가 있어요"
              onChange={() => selectDeathBenefitContext("has_minor_children")}
            />
            <DeathBenefitRadio
              checked={selectedOption === "has_major_debt"}
              label="주택담보대출·전세대출 등 큰 부채가 있어요"
              onChange={() => selectDeathBenefitContext("has_major_debt")}
            />
          </div>
        </fieldset>

        <div>
          <CoverageReference item={item} isRefreshing={isRefreshing} />

          {!item?.matched_coverage_names?.length ? (
            <p className="mt-3 text-xs leading-5 text-zinc-500">
              {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
            </p>
          ) : null}

          {item ? (
            <CoverageGroupList
              groups={item.coverage_groups ?? []}
              fallbackNames={item.matched_coverage_names ?? []}
            />
          ) : null}
        </div>
      </div>
    </CoreCoverageSection>
  );
}

function DeathBenefitRadio({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <label className="flex items-start gap-2 text-sm leading-5">
      <input
        type="radio"
        name="death-benefit-context"
        checked={checked}
        onChange={onChange}
        className="mt-0.5 size-4 border-zinc-300 text-blue-600 focus:ring-blue-500"
      />
      <span
        className={cn(
          "font-medium text-zinc-700",
          checked && "font-semibold text-blue-700",
        )}
      >
        {label}
      </span>
    </label>
  );
}
