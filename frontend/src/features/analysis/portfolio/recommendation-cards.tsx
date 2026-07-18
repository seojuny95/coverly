import type {
  CoverageGroup,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
} from "./api";
import {
  CoverageAmountMeter,
  CoverageStatusBadge,
  ReferenceSourceList,
} from "./coverage-guide";
import { formatKoreanWon } from "./money-format";

const DIAGNOSIS_KINDS = new Set<EssentialCoverageItem["kind"]>([
  "cancer",
  "cerebrovascular",
  "ischemic_heart",
]);

const RECOMMENDED_INSURANCE_COPY = {
  death: {
    title: "사망보험",
    description:
      "피보험자가 사망했을 때 남은 가족에게 정해진 보험금을 지급해요. 유가족의 생활비와 자녀 양육비, 남은 대출 상환, 장례비처럼 갑자기 생기는 재정 공백을 메우는 목적이며, 필요한 금액은 부양가족·미성년 자녀·큰 부채 여부에 따라 달라져요.",
    rangeLabel: "안내금액",
    rangeNote:
      "1인 가구 기준으로는 장례비 1,000만~2,000만원 정도부터 보고, 부양가족이 있으면 생활비까지 따로 봐야 해요.",
  },
  diagnosis: {
    title: "3대 진단보험",
    description:
      "암, 뇌혈관질환, 심장질환처럼 치료와 회복에 시간이 오래 걸리는 질병에 대비하는 보험이에요. 병원비뿐 아니라 치료 중 쉬는 기간의 생활비, 간병비, 소득 공백까지 함께 보는 보장이어서 금액은 질병별 기본 범위와 가족 부양 부담을 같이 확인해요.",
    rangeLabel: "적정 진단비 감",
  },
  medicalIndemnity: {
    title: "실손의료보험",
    description:
      "입원·통원처럼 자주 생기는 의료비 중 실제로 쓴 돈을 약관 한도 안에서 돌려받는 보험이에요.",
    rangeLabel: "확인 기준",
  },
} as const;

const DIAGNOSIS_GUIDE_COPY: Partial<
  Record<
    EssentialCoverageItem["kind"],
    {
      description: string;
    }
  >
> = {
  cancer: {
    description:
      "암으로 진단받았을 때 정해진 보험금을 한 번에 받을 수 있는 보장이에요. 급여 치료비 부담은 줄어들 수 있어도 비급여 치료, 간병, 소득 감소가 생길 수 있어 치료 중 쉬는 기간의 생활비 성격까지 함께 봐요.",
  },
  cerebrovascular: {
    description:
      "뇌출혈, 뇌경색 등 뇌혈관질환으로 진단받았을 때 받을 수 있는 보장이에요. 치료 뒤 재활, 간병, 후유장해 가능성까지 볼 수 있어 뇌출혈처럼 좁은 담보보다 뇌혈관질환 진단비 기준을 우선 확인해요.",
  },
  ischemic_heart: {
    description:
      "협심증, 급성심근경색 등 심장질환으로 진단받았을 때 받을 수 있는 보장이에요. 시술, 수술, 입원으로 소득 공백이 생길 수 있어 급성심근경색만 보는 것보다 협심증까지 포함하는 넓은 보장을 우선 확인해요.",
  },
};

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
          권장보험
        </p>
      </div>

      <div className="mt-4 space-y-4">
        <RecommendedSingleCoverageCard
          categoryLabel="사망 대비"
          item={death}
          copy={RECOMMENDED_INSURANCE_COPY.death}
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
  categoryLabel,
  item,
  copy,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isRefreshing,
}: {
  categoryLabel: string;
  item: EssentialCoverageItem | undefined;
  copy: typeof RECOMMENDED_INSURANCE_COPY.death;
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
            {categoryLabel}
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {copy.title}
          </h4>
          <p className="mt-2 text-sm leading-6 text-zinc-700">
            {copy.description}
          </p>
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
          <CoverageAmountMeter
            item={item}
            rangeLabel={copy.rangeLabel}
            fallbackNote={item?.guidance_reason ?? copy.rangeNote}
            isRefreshing={isRefreshing}
          />

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
            {RECOMMENDED_INSURANCE_COPY.diagnosis.title}
          </h4>
          <p className="mt-2 text-sm leading-6 text-zinc-700">
            {RECOMMENDED_INSURANCE_COPY.diagnosis.description}
          </p>
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
  const guide = DIAGNOSIS_GUIDE_COPY[item.kind];

  return (
    <li className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-zinc-950">{item.label}</p>
          {guide ? (
            <p className="mt-1 text-xs leading-5 text-zinc-600">
              {guide.description}
            </p>
          ) : null}
        </div>
        <CoverageStatusBadge status={item.status} />
      </div>

      <div className="mt-3">
        <CoverageAmountMeter
          item={item}
          rangeLabel={RECOMMENDED_INSURANCE_COPY.diagnosis.rangeLabel}
          fallbackNote="소득, 부양가족, 보험료 부담에 따라 달라질 수 있어요."
        />
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
            {RECOMMENDED_INSURANCE_COPY.medicalIndemnity.title}
          </h4>
          <p className="mt-2 text-sm leading-6 text-zinc-700">
            {RECOMMENDED_INSURANCE_COPY.medicalIndemnity.description}
          </p>
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
            <p className="text-xs font-semibold text-zinc-500">
              {RECOMMENDED_INSURANCE_COPY.medicalIndemnity.rangeLabel}
            </p>
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
