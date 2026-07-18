import type {
  CoverageGroup,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
} from "./api";
import { CoverageStatusBadge, ReferenceSourceList } from "./coverage-guide";
import { formatKoreanWon } from "./money-format";

const DIAGNOSIS_KINDS = new Set<EssentialCoverageItem["kind"]>([
  "cancer",
  "cerebrovascular",
  "ischemic_heart",
]);

export function recommendedDiagnosisItems(items: EssentialCoverageItem[]) {
  return items.filter((item) => DIAGNOSIS_KINDS.has(item.kind));
}

export function RecommendedInsuranceCards({
  items,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isDeathBenefitRefreshing,
}: {
  items: EssentialCoverageItem[];
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isDeathBenefitRefreshing: boolean;
}) {
  const death = items.find((item) => item.kind === "death");
  const diagnosisItems = recommendedDiagnosisItems(items);
  const medicalIndemnity = items.find(
    (item) => item.kind === "medical_indemnity",
  );
  const diagnosisConfirmedCount = diagnosisItems.filter(
    (item) => item.status !== "not_found",
  ).length;

  return (
    <article className="analysis-overview-reveal analysis-overview-delay-1 rounded-2xl border border-zinc-200 bg-white p-5 sm:p-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          핵심 보장 확인
        </p>
      </div>

      <div className="mt-4 space-y-4">
        <RecommendedSingleCoverageCard
          item={death}
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={onDeathBenefitContextChange}
          isRefreshing={isDeathBenefitRefreshing}
        />

        <RecommendedDiagnosisCard
          items={diagnosisItems}
          confirmedCount={diagnosisConfirmedCount}
        />

        <RecommendedMedicalIndemnityCard item={medicalIndemnity} />
      </div>
    </article>
  );
}

function RecommendedSingleCoverageCard({
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
    <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
            사망 보장
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {item?.label ?? "확인 결과"}
          </h4>
          {item?.guidance_situation ? (
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              {item.guidance_situation}
            </p>
          ) : null}
        </div>
        <CoverageStatusBadge
          status={item?.status ?? "not_found"}
          label={
            item?.kind === "death" && item.status === "needs_review"
              ? "점검 필요"
              : undefined
          }
        />
      </div>

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
    </section>
  );
}

function CoverageGroupList({
  groups,
  fallbackNames,
  emptyNotice,
}: {
  groups: CoverageGroup[];
  fallbackNames: string[];
  emptyNotice?: string;
}) {
  if (groups.length === 0) {
    if (fallbackNames.length === 0) {
      if (!emptyNotice) return null;
      return (
        <p className="mt-4 text-xs leading-5 text-zinc-500">{emptyNotice}</p>
      );
    }
    return (
      <p className="mt-4 text-xs leading-5 text-blue-700">
        확인된 담보: {fallbackNames.join(" · ")}
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-2">
      <p className="text-xs font-semibold text-zinc-500">확인된 담보</p>
      {groups.map((group) => (
        <div
          key={group.label}
          className={`rounded-xl border px-3 py-2 text-xs leading-5 ${coverageGroupClassName(group.tone)}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold">{group.label}</p>
            <span>
              {typeof group.total_amount === "number"
                ? `합계 ${formatKoreanWon(group.total_amount)}`
                : `${group.coverage_names?.length ?? 0}개`}
            </span>
          </div>
          <p className="mt-1">{group.coverage_names?.join(" · ")}</p>
          <p className="mt-1 opacity-80">{group.detail}</p>
        </div>
      ))}
    </div>
  );
}

function coverageGroupClassName(tone: CoverageGroup["tone"]) {
  switch (tone) {
    case "confirmed":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "review":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "limited":
      return "border-zinc-200 bg-zinc-100 text-zinc-700";
  }
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
    <label className="flex items-start gap-2 text-sm leading-5 text-zinc-700">
      <input
        type="radio"
        name="death-benefit-context"
        checked={checked}
        onChange={onChange}
        className="mt-0.5 size-4 border-zinc-300 text-blue-600 focus:ring-blue-500"
      />
      <span>{label}</span>
    </label>
  );
}

function RecommendedDiagnosisCard({
  items,
  confirmedCount,
}: {
  items: EssentialCoverageItem[];
  confirmedCount: number;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
            진단 이후 생활
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            진단 보장
          </h4>
        </div>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-200">
          {confirmedCount}/3 확인
        </span>
      </div>

      <ul className="mt-5 grid gap-3 border-t border-zinc-200 pt-5 lg:grid-cols-3">
        {items.map((item) => (
          <RecommendedDiagnosisItem key={item.kind} item={item} />
        ))}
      </ul>
    </section>
  );
}

function RecommendedDiagnosisItem({ item }: { item: EssentialCoverageItem }) {
  return (
    <li className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-zinc-950">{item.label}</p>
          {item.guidance_situation ? (
            <p className="mt-1 text-xs leading-5 text-zinc-600">
              {item.guidance_situation}
            </p>
          ) : null}
        </div>
        <CoverageStatusBadge status={item.status} />
      </div>

      <div className="mt-3">
        <CoverageReference item={item} />
      </div>

      <CoverageGroupList
        groups={item.coverage_groups ?? []}
        fallbackNames={item.matched_coverage_names ?? []}
        emptyNotice="현재 업로드된 보험증권에서는 해당 보장이 확인되지 않아요"
      />
    </li>
  );
}

function RecommendedMedicalIndemnityCard({
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
        <div className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
          <p className="text-xs font-semibold text-zinc-500">현재 확인 결과</p>
          <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-zinc-950">
            {medicalIndemnityHeadline(item)}
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">
            {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
          </p>
        </div>

        {item?.reference_basis ? (
          <div className="rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3">
            <p className="text-xs font-semibold text-zinc-500">확인 기준</p>
            <p className="mt-1 text-sm leading-6 text-zinc-700">
              {item.reference_basis}
            </p>
            <ReferenceSourceList sources={item.reference_sources ?? []} />
          </div>
        ) : null}
      </div>

      <CoverageNamesNotice names={item?.matched_coverage_names ?? []} />
    </section>
  );
}

function CoverageReference({
  item,
  isRefreshing = false,
}: {
  item: EssentialCoverageItem | undefined;
  isRefreshing?: boolean;
}) {
  if (isRefreshing) {
    return (
      <div
        role="status"
        aria-label="참고 금액을 다시 확인하고 있어요"
        aria-busy="true"
        aria-live="polite"
        className="h-28 animate-pulse rounded-2xl bg-zinc-100"
      />
    );
  }

  if (!item) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-500">
        확인 결과를 불러오지 못했어요.
      </div>
    );
  }

  const referenceAmount =
    item.reference_amount_label ??
    formatReferenceAmount(item.reference_min_amount, item.reference_max_amount);

  return (
    <div className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold text-zinc-500">현재 가입금액</p>
          <p className="mt-1 text-lg font-semibold text-zinc-950">
            {item.confirmed_amount == null
              ? "미확인"
              : formatKoreanWon(item.confirmed_amount)}
          </p>
        </div>
        {referenceAmount ? (
          <div>
            <p className="text-xs font-semibold text-zinc-500">참고 금액</p>
            <p className="mt-1 text-sm font-medium text-zinc-700">
              {referenceAmount}
            </p>
          </div>
        ) : null}
      </div>
      {item.reference_basis ? (
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          {item.reference_basis}
        </p>
      ) : null}
      {item.guidance_reason && item.guidance_reason !== item.reference_basis ? (
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          {item.guidance_reason}
        </p>
      ) : null}
      <ReferenceSourceList sources={item.reference_sources ?? []} />
    </div>
  );
}

function formatReferenceAmount(
  minAmount: number | null | undefined,
  maxAmount: number | null | undefined,
) {
  if (minAmount == null || maxAmount == null) return null;
  if (minAmount === maxAmount) return formatKoreanWon(minAmount);
  return `${formatKoreanWon(minAmount)} ~ ${formatKoreanWon(maxAmount)}`;
}

function CoverageNamesNotice({ names }: { names: string[] }) {
  if (names.length === 0) {
    return (
      <p className="mt-4 text-xs leading-5 text-zinc-500">
        현재 업로드된 보험증권에서는 해당 보장이 확인되지 않아요
      </p>
    );
  }

  return (
    <p className="mt-4 text-xs leading-5 text-blue-700">
      확인된 담보: {names.join(" · ")}
    </p>
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
