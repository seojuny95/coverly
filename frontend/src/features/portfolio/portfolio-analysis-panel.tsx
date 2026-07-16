import type { CSSProperties, ReactNode } from "react";

import { primaryButtonClassName } from "../../components/coverly-brand";
import type { EmptyReason } from "./analysis-eligibility";
import { formatKoreanWon, formatWon } from "./money-format";
import type {
  ClaimChannelBlock,
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  PortfolioSummary,
  ReferenceSource,
  SourceReliability,
  SpecialPolicyAnalysis,
} from "./portfolio-api";
import { safeHref } from "./safe-href";

const EMPTY_COPY: Record<EmptyReason, { title: string; description: string }> =
  {
    "auto-only": {
      title: "확인할 보험 정보가 없어요",
      description:
        "담보 내용이 있는 보험증권을 올리면 전체 보험을 확인할 수 있어요.",
    },
    "no-coverage": {
      title: "확인할 담보가 없어요",
      description:
        "담보 내용이 있는 보험증권을 올리면 전체 보험을 확인할 수 있어요.",
    },
    mixed: {
      title: "확인할 담보가 없어요",
      description:
        "담보 내용이 있는 보험증권을 올리면 전체 보험을 확인할 수 있어요.",
    },
  };

const STATUS_COPY = {
  well_prepared: {
    label: "가입 확인",
    className: "bg-emerald-50 text-emerald-700",
    dotClassName: "bg-emerald-500",
  },
  needs_review: {
    label: "중복 가능성 확인",
    className: "bg-amber-50 text-amber-800",
    dotClassName: "bg-amber-500",
  },
  not_found: {
    label: "현재 자료에서 미확인",
    className: "bg-zinc-100 text-zinc-600",
    dotClassName: "bg-zinc-400",
  },
} as const;

const DIAGNOSIS_KINDS = new Set<EssentialCoverageItem["kind"]>([
  "cancer",
  "cerebrovascular",
  "ischemic_heart",
]);

const RECOMMENDED_INSURANCE_COPY = {
  death: {
    title: "사망보험",
    description:
      "유가족 생활비가 기본이고 남은 대출 상환·장례비·상속세 재원으로도 쓸 수 있어 먼저 확인해요.",
    rangeLabel: "안내금액",
    rangeNote:
      "1인 가구 기준으로는 장례비 1,000만~2,000만원 정도부터 보고, 부양가족이 있으면 생활비까지 따로 봐야 해요.",
  },
  diagnosis: {
    title: "3대 진단보험",
    description:
      "암, 뇌혈관질환, 심장질환처럼 치료와 회복에 시간이 오래 걸리는 질병에 대비해 치료비뿐 아니라 쉬는 동안의 생활비와 간병비까지 준비해주는 보험이에요.",
    rangeLabel: "적정 진단비 감",
    rangeNote:
      "3대 진단비는 치료비만을 위한 돈이 아니라, 치료와 회복으로 일을 쉬는 동안의 생활비까지 대비하는 금액이에요. 일반적으로 암 진단비는 3천만~5천만 원, 뇌혈관·심장질환 진단비는 각각 1천만~2천만 원을 기본 범위로 보고, 소득이나 가족 부양 부담이 크다면 더 높게 준비할 수 있어요.",
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
      rationale: string;
    }
  >
> = {
  cancer: {
    description:
      "암으로 진단받았을 때 정해진 보험금을 한 번에 받을 수 있는 보장이에요.",
    rationale:
      "암은 건강보험 산정특례로 급여 치료비 부담은 줄어들 수 있지만, 비급여 치료비·생활비·소득감소가 문제예요. 그래서 암 진단비는 단순 병원비보다 치료 중 쉬는 기간의 생활비 성격이 커요.",
  },
  cerebrovascular: {
    description:
      "뇌출혈, 뇌경색 등 뇌혈관질환으로 진단받았을 때 받을 수 있는 보장이에요.",
    rationale:
      "뇌혈관질환은 치료 이후 재활, 간병, 후유장해 가능성이 있어요. 보장 범위는 뇌출혈보다 뇌혈관질환이 넓기 때문에 가능하면 뇌혈관질환 진단비 기준으로 보는 게 좋아요.",
  },
  ischemic_heart: {
    description:
      "협심증, 급성심근경색 등 심장질환으로 진단받았을 때 받을 수 있는 보장이에요.",
    rationale:
      "심장질환은 갑작스럽게 발생하고, 진단 후 시술·수술·입원으로 소득 공백이 생길 수 있어요. 급성심근경색만 보는 것보다 허혈성심장질환처럼 협심증까지 포함하는 넓은 보장을 우선으로 보는 게 좋아요.",
  },
};

export function PortfolioAnalysisPanel({
  status,
  summary,
  deathBenefitContext,
  onDeathBenefitContextChange,
  eligibleCount,
  emptyReason,
  onRetry,
}: {
  status: "loading" | "success" | "error";
  summary?: PortfolioSummary;
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  eligibleCount: number;
  emptyReason: EmptyReason;
  onRetry: () => void;
}) {
  if (eligibleCount === 0) return <InfoState {...EMPTY_COPY[emptyReason]} />;
  if (status === "loading") return <AnalysisLoading />;

  if (status === "error") {
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">
          보장 점검 결과를 불러오지 못했어요
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          업로드한 증권은 그대로 있어요. 잠시 후 다시 확인해주세요.
        </p>
        <button
          type="button"
          className={`mt-5 ${primaryButtonClassName}`}
          onClick={onRetry}
        >
          다시 확인하기
        </button>
      </section>
    );
  }

  const items = summary?.essential_coverage_check?.items ?? [];
  const specialAnalyses = summary?.special_policy_analyses ?? [];

  return (
    <div className="space-y-8">
      <PortfolioOverview
        summary={summary}
        items={items}
        deathBenefitContext={deathBenefitContext}
        onDeathBenefitContextChange={onDeathBenefitContextChange}
        policyCount={eligibleCount}
        specialAnalyses={specialAnalyses}
        onRetry={onRetry}
      />

      {specialAnalyses.length > 0 ? (
        <SpecialPolicySections analyses={specialAnalyses} />
      ) : null}

      <ClaimGuide claimChannels={summary?.claim_channels ?? null} />
    </div>
  );
}

function PortfolioOverview({
  summary,
  items,
  deathBenefitContext,
  onDeathBenefitContextChange,
  policyCount,
  specialAnalyses,
  onRetry,
}: {
  summary?: PortfolioSummary;
  items: EssentialCoverageItem[];
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  policyCount: number;
  specialAnalyses: SpecialPolicyAnalysis[];
  onRetry: () => void;
}) {
  const diagnosisItems = items.filter((item) => DIAGNOSIS_KINDS.has(item.kind));
  const confirmedDiagnosisCount = diagnosisItems.filter(
    (item) => item.status !== "not_found",
  ).length;
  const premium = summary?.premium ?? null;
  const premiumBenchmark = summary?.premium_benchmark ?? null;
  const premiumComparison = premiumSummaryComparison(
    premium,
    premiumBenchmark,
    items,
  );
  const generatedOverview = summary?.overview ?? null;

  if (!generatedOverview) {
    return (
      <section aria-labelledby="portfolio-overview-title" className="space-y-4">
        <div className="rounded-[28px] border border-zinc-200 bg-zinc-950 px-6 py-8 text-white sm:px-8">
          <p className="font-mono text-[11px] font-semibold tracking-[0.16em] text-blue-300 uppercase">
            전체 보험 총평
          </p>
          <h2
            id="portfolio-overview-title"
            className="mt-3 text-2xl font-semibold tracking-[-0.04em]"
          >
            총평을 생성하지 못했어요
          </h2>
          <p className="mt-3 text-sm leading-6 text-zinc-300">
            확인된 보장 정보는 그대로예요. 잠시 후 총평을 다시 생성해주세요.
          </p>
          <button
            type="button"
            className={`mt-5 ${primaryButtonClassName}`}
            onClick={onRetry}
          >
            총평 다시 생성하기
          </button>
        </div>

        <RecommendedInsuranceCards
          items={items}
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={onDeathBenefitContextChange}
        />
        <ActualLossCoverageReview
          coverages={summary?.actual_loss_coverages ?? []}
        />
      </section>
    );
  }

  return (
    <section aria-labelledby="portfolio-overview-title" className="space-y-4">
      <div className="analysis-overview-reveal relative overflow-hidden rounded-[28px] border border-blue-200 bg-zinc-950 px-6 py-7 text-white shadow-[10px_10px_0_#e8edff] sm:px-8 sm:py-9">
        <div className="analysis-overview-grid pointer-events-none absolute inset-0" />
        <div className="relative">
          <div className="min-w-0">
            <p className="font-mono text-[11px] font-semibold tracking-[0.16em] text-blue-300 uppercase">
              전체 보험 총평
            </p>
            <h2
              id="portfolio-overview-title"
              className="mt-3 max-w-2xl text-2xl font-semibold tracking-[-0.045em] text-balance sm:text-3xl"
            >
              {generatedOverview.title}
            </h2>
            <div className="mt-4 max-w-3xl space-y-3 text-sm leading-7 text-pretty text-zinc-300">
              {generatedOverview.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>

            <div className="mt-6 grid gap-3 border-y border-white/10 py-4 text-sm sm:grid-cols-3">
              {generatedOverview.takeaways.map((takeaway) => (
                <div key={takeaway.label} className="min-w-0">
                  <p className="text-[11px] font-semibold tracking-[0.12em] text-blue-300 uppercase">
                    {takeaway.label}
                  </p>
                  <p className="mt-1 font-semibold text-white">
                    {takeaway.title}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-zinc-400">
                    {takeaway.detail}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-5 flex flex-wrap gap-2 text-xs text-zinc-300">
              {premiumComparison ? (
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                  월 보험료 {formatWon(premium?.monthly_total ?? null)}
                </span>
              ) : null}
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                올린 증권 {policyCount}건
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                3대 진단비 {confirmedDiagnosisCount}/3
              </span>
              {specialAnalyses.length > 0 ? (
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
                  손해보험 {specialAnalyses.length}종
                </span>
              ) : null}
            </div>

            {premiumComparison ? (
              <PremiumSummaryBar
                premium={premium}
                benchmark={premiumBenchmark}
                comparison={premiumComparison}
              />
            ) : null}
          </div>
        </div>
      </div>

      <RecommendedInsuranceCards
        items={items}
        deathBenefitContext={deathBenefitContext}
        onDeathBenefitContextChange={onDeathBenefitContextChange}
      />
      <ActualLossCoverageReview
        coverages={summary?.actual_loss_coverages ?? []}
      />
    </section>
  );
}

function RecommendedInsuranceCards({
  items,
  deathBenefitContext,
  onDeathBenefitContextChange,
}: {
  items: EssentialCoverageItem[];
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
}) {
  const death = items.find((item) => item.kind === "death");
  const diagnosisItems = items.filter((item) => DIAGNOSIS_KINDS.has(item.kind));
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

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.05fr_1.25fr_1fr]">
        <RecommendedSingleCoverageCard
          eyebrow="사망 대비"
          item={death}
          copy={RECOMMENDED_INSURANCE_COPY.death}
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={onDeathBenefitContextChange}
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

function duplicateActualLossCoverageNames(
  coverages: PortfolioSummary["actual_loss_coverages"],
) {
  const namesByNormalizedName = new Map<string, string>();
  for (const coverage of coverages) {
    if (!coverage.duplicate_across_contracts) continue;
    const key = coverage.normalized_name || coverage.coverage_name;
    if (!namesByNormalizedName.has(key)) {
      namesByNormalizedName.set(key, coverage.coverage_name);
    }
  }
  return [...namesByNormalizedName.values()];
}

function ActualLossCoverageReview({
  coverages,
}: {
  coverages: PortfolioSummary["actual_loss_coverages"];
}) {
  const duplicateNames = duplicateActualLossCoverageNames(coverages);

  return (
    <article className="analysis-overview-reveal analysis-overview-delay-2 rounded-2xl border border-zinc-200 bg-white p-5 sm:p-6">
      <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
        실손형 지급 방식
      </p>
      <h3 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
        실손형 보장 중복 점검
      </h3>
      <p className="mt-3 text-sm leading-6 text-zinc-700">
        실제 발생한 손해를 보상하는 담보는 같은 손해를 여러 계약에서 보장하는지
        따로 확인해요. 실손의료보험 가입 여부 점검과는 다른 항목이에요.
      </p>
      {duplicateNames.length > 0 ? (
        <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
          여러 계약에서 확인된 실손형 담보: {duplicateNames.join(" · ")}. 실제
          중복 보상 제한은 각 약관에서 확인해요.
        </p>
      ) : coverages.length > 0 ? (
        <p className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-600">
          같은 실손형 담보가 여러 계약에서 확인되지는 않았어요.
        </p>
      ) : (
        <p className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-600">
          현재 자료에서는 실손형 담보를 확인하지 못했어요.
        </p>
      )}
    </article>
  );
}

function RecommendedSingleCoverageCard({
  eyebrow,
  item,
  copy,
  deathBenefitContext,
  onDeathBenefitContextChange,
}: {
  eyebrow: string;
  item: EssentialCoverageItem | undefined;
  copy: typeof RECOMMENDED_INSURANCE_COPY.death;
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
}) {
  const updateDeathBenefitContext = (
    key: keyof DeathBenefitGuideInput,
    checked: boolean,
  ) => {
    onDeathBenefitContextChange({ ...deathBenefitContext, [key]: checked });
  };

  return (
    <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
            {eyebrow}
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {copy.title}
          </h4>
        </div>
        <CoverageStatusBadge status={item?.status ?? "not_found"} />
      </div>

      <p className="mt-4 text-sm leading-6 text-zinc-700">{copy.description}</p>

      <div className="mt-4 space-y-2 rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
        <p className="text-xs font-semibold text-zinc-500">나의 상황</p>
        <DeathBenefitCheckbox
          checked={deathBenefitContext.has_dependent_family}
          label="내 소득에 의존하는 가족이 있어요"
          onChange={(checked) =>
            updateDeathBenefitContext("has_dependent_family", checked)
          }
        />
        <DeathBenefitCheckbox
          checked={deathBenefitContext.has_minor_children}
          label="미성년 자녀가 있어요"
          onChange={(checked) =>
            updateDeathBenefitContext("has_minor_children", checked)
          }
        />
        <DeathBenefitCheckbox
          checked={deathBenefitContext.has_major_debt}
          label="주택담보대출·전세대출 등 큰 부채가 있어요"
          onChange={(checked) =>
            updateDeathBenefitContext("has_major_debt", checked)
          }
        />
      </div>

      {item?.guidance_situation ? (
        <div className="mt-4 rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
          <p className="text-xs font-semibold text-zinc-500">상황</p>
          <p className="mt-1 text-sm font-semibold text-zinc-950">
            {item.guidance_situation}
          </p>
        </div>
      ) : null}

      <div className="mt-5">
        <CoverageAmountMeter
          item={item}
          rangeLabel={copy.rangeLabel}
          fallbackNote={item?.guidance_reason ?? copy.rangeNote}
        />
      </div>

      <p className="mt-3 text-xs leading-5 text-zinc-500">
        {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
      </p>

      {item?.matched_coverage_names.length ? (
        <p className="mt-4 text-xs leading-5 text-blue-700">
          확인된 담보: {item.matched_coverage_names.join(" · ")}
        </p>
      ) : null}
    </section>
  );
}

function DeathBenefitCheckbox({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2 text-sm leading-5 text-zinc-700">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.currentTarget.checked)}
        className="mt-0.5 size-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
            진단 이후 생활
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {RECOMMENDED_INSURANCE_COPY.diagnosis.title}
          </h4>
        </div>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-200">
          {confirmedCount}/3 확인
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-zinc-700">
        {RECOMMENDED_INSURANCE_COPY.diagnosis.description}
      </p>

      <ul className="mt-5 space-y-3">
        {items.map((item) => (
          <RecommendedDiagnosisItem key={item.kind} item={item} />
        ))}
      </ul>

      <p className="mt-4 rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3 text-xs leading-5 text-zinc-600">
        {RECOMMENDED_INSURANCE_COPY.diagnosis.rangeNote}
      </p>
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
          <p className="mt-1 text-xs leading-5 text-zinc-500">{item.detail}</p>
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

      {guide ? (
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          {guide.rationale}
        </p>
      ) : null}
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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
            실제 의료비
          </p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {RECOMMENDED_INSURANCE_COPY.medicalIndemnity.title}
          </h4>
        </div>
        <CoverageStatusBadge status={item?.status ?? "not_found"} />
      </div>

      <p className="mt-4 text-sm leading-6 text-zinc-700">
        {RECOMMENDED_INSURANCE_COPY.medicalIndemnity.description}
      </p>

      <div className="mt-5 rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
        <p className="text-xs font-semibold text-zinc-500">현재 확인 결과</p>
        <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-zinc-950">
          {medicalIndemnityHeadline(item)}
        </p>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
        </p>
      </div>

      {item?.reference_basis ? (
        <div className="mt-4 rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3">
          <p className="text-xs font-semibold text-zinc-500">
            {RECOMMENDED_INSURANCE_COPY.medicalIndemnity.rangeLabel}
          </p>
          <p className="mt-1 text-sm leading-6 text-zinc-700">
            {item.reference_basis}
          </p>
          <ReferenceSourceList sources={item.reference_sources} />
        </div>
      ) : null}

      {item?.matched_coverage_names.length ? (
        <p className="mt-4 text-xs leading-5 text-blue-700">
          확인된 담보: {item.matched_coverage_names.join(" · ")}
        </p>
      ) : null}
    </section>
  );
}

function CoverageStatusBadge({
  status,
}: {
  status: EssentialCoverageItem["status"];
}) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_COPY[status].className}`}
    >
      {STATUS_COPY[status].label}
    </span>
  );
}

function CoverageAmountMeter({
  item,
  rangeLabel,
  fallbackNote,
}: {
  item: EssentialCoverageItem | undefined;
  rangeLabel: string;
  fallbackNote: string;
}) {
  const currentAmount = item?.confirmed_amount ?? null;
  const minAmount = item?.reference_min_amount ?? null;
  const maxAmount = item?.reference_max_amount ?? null;
  const basis = item?.reference_basis ?? fallbackNote;
  const sources = item?.reference_sources ?? [];
  const amountLabel = item?.reference_amount_label ?? null;

  if (minAmount == null || maxAmount == null) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold text-zinc-500">{rangeLabel}</p>
        <p className="mt-1 text-sm leading-6 text-zinc-700">{basis}</p>
        <ReferenceSourceList sources={sources} />
      </div>
    );
  }

  const scaleMax = Math.max(currentAmount ?? 0, maxAmount) * 1.2 || maxAmount;
  const minPosition = progressPosition(minAmount, scaleMax);
  const maxPosition = progressPosition(maxAmount, scaleMax);
  const currentPosition = progressPosition(currentAmount ?? 0, scaleMax);
  const isRange = minAmount !== maxAmount;
  const style = {
    "--premium-position": `${currentPosition}%`,
  } as CSSProperties;

  return (
    <div className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-zinc-500">현재 가입금액</p>
          <p className="mt-1 text-lg font-semibold text-zinc-950">
            {currentAmount ? formatKoreanWon(currentAmount) : "미확인"}
          </p>
        </div>
        <div className="text-right text-xs leading-5 text-zinc-500">
          <p>{rangeLabel}</p>
          <p className="font-medium text-zinc-700">
            {amountLabel ??
              `${formatKoreanWon(minAmount)}${
                minAmount !== maxAmount
                  ? ` ~ ${formatKoreanWon(maxAmount)}`
                  : ""
              }`}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="relative h-24" style={style}>
          <div className="absolute inset-x-0 top-10 h-2 rounded-full bg-zinc-100" />
          <div className="premium-position-fill absolute top-10 left-0 z-10 h-2 rounded-full bg-blue-600" />
          <div
            className="absolute top-10 z-20 h-2 rounded-full bg-emerald-300/60 ring-2 ring-white/80"
            style={{
              left: `${minPosition}%`,
              width: `${Math.max(maxPosition - minPosition, 4)}%`,
            }}
          />
          {isRange ? (
            <>
              <RangeArrow left={minPosition} label="권장" tone="emerald" />
              <RangeArrow left={maxPosition} label="권장" tone="emerald" />
            </>
          ) : (
            <RangeArrow left={minPosition} label="권장" tone="emerald" />
          )}
          <span
            aria-hidden="true"
            className="absolute top-9 z-40 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white bg-blue-600 shadow-sm"
            style={{ left: `${currentPosition}%` }}
          />
          <PositionLabel left={currentPosition}>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap text-blue-700 ring-1 ring-blue-100/80">
              {currentAmount ? formatKoreanWon(currentAmount) : "미확인"}
            </span>
          </PositionLabel>
          <div className="absolute inset-x-0 top-20 flex justify-between text-[11px] text-zinc-400">
            <span>0원</span>
            <span>{formatKoreanWon(Math.round(scaleMax))}</span>
          </div>
        </div>
      </div>

      <p className="mt-3 text-xs leading-5 text-zinc-500">{basis}</p>
      <ReferenceSourceList sources={sources} />
    </div>
  );
}

function ReferenceSourceList({
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

function sourceTypeLabel(reliability: SourceReliability) {
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

function medicalIndemnityHeadline(item: EssentialCoverageItem | undefined) {
  if (!item || item.status === "not_found") {
    return "가입 여부 미확인";
  }
  if (item.status === "needs_review") {
    return `${item.coverage_count}건 확인`;
  }
  return "가입 확인";
}

function SpecialPolicySections({
  analyses,
}: {
  analyses: SpecialPolicyAnalysis[];
}) {
  return (
    <section aria-labelledby="policy-type-title">
      <h2 id="policy-type-title" className="text-xl font-semibold">
        손해보험 분석
      </h2>
      <p className="mt-1 text-sm leading-6 text-zinc-500">
        가입한 손해보험의 담보명을 읽어 주요 보장 영역별로 확인했어요.
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {analyses.map((analysis) => (
          <article
            key={analysis.kind}
            className="analysis-overview-reveal overflow-hidden rounded-2xl border border-zinc-200 bg-white"
          >
            <div className="border-b border-zinc-100 bg-zinc-50 px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold">{analysis.label}</h3>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs text-zinc-600 ring-1 ring-zinc-200">
                  {analysis.policy_count}건
                </span>
              </div>
              <p className="mt-2 text-xs font-medium text-zinc-500">
                {analysis.product_names.join(" · ")}
              </p>
              {analysis.classification_reasons?.length ? (
                <p className="mt-2 text-xs leading-5 text-zinc-500">
                  {analysis.classification_reasons.join(" ")}
                </p>
              ) : null}
              <p className="mt-3 text-sm leading-6 text-zinc-700">
                {analysis.overview}
              </p>
            </div>

            <ul className="divide-y divide-zinc-100 px-5">
              {analysis.coverage_checks.map((check) => (
                <li key={check.label} className="py-4">
                  <div className="flex items-start gap-3">
                    <span
                      className={`mt-1.5 size-2 shrink-0 rounded-full ${
                        check.status === "confirmed"
                          ? "bg-emerald-500"
                          : "bg-zinc-300"
                      }`}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-zinc-900">
                          {check.label}
                        </p>
                        <span
                          className={`text-[11px] font-medium ${
                            check.status === "confirmed"
                              ? "text-emerald-700"
                              : "text-zinc-500"
                          }`}
                        >
                          {check.status === "confirmed"
                            ? "담보 확인"
                            : "현재 자료에서 미확인"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-zinc-500">
                        {check.detail}
                      </p>
                      {check.matched_coverage_names.length > 0 ? (
                        <p className="mt-1.5 truncate text-xs text-blue-700">
                          {check.matched_coverage_names.join(" · ")}
                        </p>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function PremiumSummaryBar({
  premium,
  benchmark,
  comparison,
}: {
  premium: PortfolioSummary["premium"];
  benchmark: PortfolioSummary["premium_benchmark"];
  comparison: {
    label: string;
    title: string;
  };
}) {
  if (
    !premium ||
    !benchmark ||
    typeof premium.monthly_total !== "number" ||
    premium.monthly_policy_count < 1
  ) {
    return null;
  }

  const maxAmount =
    Math.max(premium.monthly_total, benchmark.suggested_max_premium) * 1.2;
  const minPosition = progressPosition(
    benchmark.suggested_min_premium,
    maxAmount,
  );
  const maxPosition = progressPosition(
    benchmark.suggested_max_premium,
    maxAmount,
  );
  const userPosition = progressPosition(premium.monthly_total, maxAmount);
  const sourceLabels = [
    sourceTypeLabel(benchmark.income_source.reliability),
    sourceTypeLabel(benchmark.guide_source.reliability),
  ];
  const style = {
    "--premium-position": `${userPosition}%`,
  } as CSSProperties;

  return (
    <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-blue-200">
            매달 내는 보험료
          </p>
          <p className="mt-1 text-lg font-semibold tracking-[-0.03em] text-white">
            {comparison.label}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-zinc-400">
            {benchmark.age_band_label} 평균 소득 기준
          </p>
          <p className="mt-1 text-sm font-medium text-zinc-200">
            {formatWon(benchmark.suggested_min_premium)} ~{" "}
            {formatWon(benchmark.suggested_max_premium)}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="relative h-24" style={style}>
          <div className="absolute inset-x-0 top-10 h-2 rounded-full bg-white/10" />
          <div className="premium-position-fill absolute top-10 left-0 z-10 h-2 rounded-full bg-blue-400" />
          <div
            className="absolute top-10 z-20 h-2 rounded-full bg-emerald-300/55 ring-1 ring-white/15"
            style={{
              left: `${minPosition}%`,
              width: `${Math.max(maxPosition - minPosition, 4)}%`,
            }}
          />
          <RangeArrow left={minPosition} label="권장 5%" tone="white" />
          <RangeArrow left={maxPosition} label="권장 10%" tone="white" />
          <span
            aria-hidden="true"
            className="absolute top-9 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-zinc-950 bg-blue-300 shadow-sm"
            style={{ left: `${userPosition}%` }}
          />
          <PositionLabel left={userPosition}>
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap text-blue-900">
              {formatWon(premium.monthly_total)}
            </span>
          </PositionLabel>
          <div className="absolute inset-x-0 top-20 flex justify-between text-[11px] text-zinc-400">
            <span>0원</span>
            <span>{formatWon(Math.round(maxAmount))}</span>
          </div>
        </div>
      </div>

      <p className="mt-3 text-xs leading-5 text-zinc-300">
        월 소득의 {Math.round(benchmark.suggested_min_ratio * 100)}%~
        {Math.round(benchmark.suggested_max_ratio * 100)} 권장 구간과
        비교했어요. {sourceLabels.join(" + ")} 기준이에요.
      </p>
      <ReferenceSourceList
        sources={[benchmark.income_source, benchmark.guide_source]}
        className="[&_a]:border-white/10 [&_a]:bg-white/10 [&_a]:text-zinc-200 [&_span]:border-white/10 [&_span]:bg-white/10 [&_span]:text-zinc-200"
      />
    </div>
  );
}

function premiumSummaryComparison(
  premium: PortfolioSummary["premium"] | null | undefined,
  benchmark: PortfolioSummary["premium_benchmark"] | null | undefined,
  items: EssentialCoverageItem[],
) {
  if (
    !premium ||
    !benchmark ||
    typeof premium.monthly_total !== "number" ||
    premium.monthly_policy_count < 1
  ) {
    return null;
  }

  const allCoreCoverageVisible = items.every(
    (item) => item.status !== "not_found",
  );

  if (premium.monthly_total < benchmark.suggested_min_premium) {
    return {
      tone: "low" as const,
      label: allCoreCoverageVisible
        ? "현재 보험료는 좋아보여요"
        : "권장보험을 점검해보세요",
      title: allCoreCoverageVisible
        ? "현재 보험료는 좋아보여요"
        : "권장보험을 점검해보세요",
    };
  }
  if (premium.monthly_total > benchmark.suggested_max_premium) {
    return {
      tone: "high" as const,
      label: "현재 보험료는 높아보여요",
      title: "현재 보험료는 높아보여요",
    };
  }
  return {
    tone: "in_range" as const,
    label: allCoreCoverageVisible
      ? "현재 보험료는 좋아보여요"
      : "권장보험을 점검해보세요",
    title: allCoreCoverageVisible
      ? "현재 보험료는 좋아보여요"
      : "권장보험을 점검해보세요",
  };
}

function RangeArrow({
  left,
  label,
  tone,
}: {
  left: number;
  label: string;
  tone: "emerald" | "white";
}) {
  const labelClassName =
    tone === "white"
      ? "bg-white/10 text-zinc-100 ring-1 ring-white/10"
      : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
  const arrowClassName =
    tone === "white" ? "text-zinc-200" : "text-emerald-500";

  return (
    <div
      className="absolute top-0 z-50 flex h-10 -translate-x-1/2 flex-col items-center justify-end"
      style={{ left: `${left}%` }}
    >
      <span
        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${labelClassName}`}
      >
        {label}
      </span>
      <span
        aria-hidden="true"
        className={`-mb-px h-0 w-0 border-x-[5px] border-t-[7px] border-x-transparent ${arrowClassName}`}
      />
    </div>
  );
}

function PositionLabel({
  left,
  children,
}: {
  left: number;
  children: ReactNode;
}) {
  const alignmentClassName =
    left <= 5
      ? "translate-x-0"
      : left >= 95
        ? "-translate-x-full"
        : "-translate-x-1/2";

  return (
    <div
      className={`absolute top-14 z-40 ${alignmentClassName}`}
      style={{ left: `${left}%` }}
    >
      {children}
    </div>
  );
}

function progressPosition(amount: number, maxAmount: number) {
  if (!Number.isFinite(amount) || maxAmount <= 0) return 0;
  return Math.min((amount / maxAmount) * 100, 100);
}

function ClaimGuide({
  claimChannels,
}: {
  claimChannels: ClaimChannelBlock | null;
}) {
  const steps = [
    {
      title: "보장 대상인지 먼저 확인",
      description:
        "사고·진단 일자와 내용을 정리하고, 증권과 약관에서 해당 위험이 보장되는지 살펴봐요.",
    },
    {
      title: "청구 서류 준비",
      description:
        "공통으로 청구서와 신분증을 준비해요. 진단비는 진단서, 실손의료비는 진료비 계산서·영수증과 세부내역서가 기본이에요.",
    },
    {
      title: "청구 채널 선택",
      description:
        "실손의료비는 실손24와 보험사 채널 중에서 고를 수 있어요. 그 외 보험금은 보험사 앱·홈페이지·우편·방문 중 가능한 방법으로 접수해요.",
    },
    {
      title: "접수와 심사 결과 확인",
      description:
        "접수번호와 담당자를 확인하고, 추가 서류 요청이나 지급 결과를 살펴봐요. 청구권은 일반적으로 사고 발생 후 3년 안에 행사해야 해요.",
    },
  ];

  return (
    <section aria-labelledby="claim-guide-title">
      <div className="rounded-[28px] border border-zinc-200 bg-zinc-50 p-5 sm:p-7">
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          보험금 청구 방법
        </p>
        <h2 id="claim-guide-title" className="mt-2 text-xl font-semibold">
          접수까지 네 단계로 준비해요
        </h2>
        <ol className="mt-6 space-y-3">
          {steps.map((step, index) => (
            <li
              key={step.title}
              className="rounded-2xl border border-zinc-200 bg-white p-4"
            >
              <div className="flex gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-blue-600 font-mono text-sm font-semibold text-white">
                  {index + 1}
                </span>
                <div>
                  <h3 className="text-sm font-semibold">{step.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-600">
                    {step.description}
                  </p>
                  {index === 2 && claimChannels?.medical_indemnity ? (
                    <div className="mt-3 space-y-3">
                      <div className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2.5 text-xs leading-5 text-zinc-600">
                        <p className="font-semibold text-zinc-900">
                          {claimChannels.medical_indemnity.name}
                        </p>
                        {claimChannels.medical_indemnity.description ? (
                          <p className="mt-1">
                            {claimChannels.medical_indemnity.description}
                          </p>
                        ) : null}
                        <p className="mt-1">
                          참여 병원이라면 진료비 서류를 전자 전송할 수 있어요.
                          먼저 연계 병원인지 확인해요.
                        </p>
                        {claimChannels.medical_indemnity.call_center ? (
                          <p className="mt-1 text-zinc-500">
                            콜센터 {claimChannels.medical_indemnity.call_center}
                          </p>
                        ) : null}
                        <ChannelLinkList
                          links={claimChannels.medical_indemnity.links}
                          className="mt-2"
                        />
                      </div>

                      {claimChannels.insurers.length ? (
                        <details className="rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 marker:content-none [&::-webkit-details-marker]:hidden">
                            <span>
                              <span className="text-sm font-semibold text-zinc-900">
                                가입한 보험사 청구 채널 보기
                              </span>
                              <span className="mt-1 block text-xs text-zinc-500">
                                실손의료비도 보험사 앱이나 홈페이지에서 직접
                                청구할 수 있어요.
                              </span>
                            </span>
                            <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-medium text-zinc-600">
                              {claimChannels.insurers.length}곳
                            </span>
                          </summary>

                          <ul className="mt-3 space-y-3 border-t border-zinc-100 pt-3 text-xs leading-5 text-zinc-600">
                            {claimChannels.insurers.map((insurer) => (
                              <li
                                key={insurer.name}
                                className="rounded-lg bg-zinc-50 p-3"
                              >
                                <p className="font-semibold text-zinc-900">
                                  {insurer.name}
                                </p>
                                {insurer.customer_center ? (
                                  <p className="mt-1 text-zinc-500">
                                    고객센터 {insurer.customer_center}
                                  </p>
                                ) : null}
                                {insurer.note ? (
                                  <p className="mt-1 text-zinc-500">
                                    {insurer.note}
                                  </p>
                                ) : null}
                                <ChannelLinkList
                                  links={insurer.links}
                                  className="mt-2"
                                />
                              </li>
                            ))}
                          </ul>
                        </details>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm font-semibold text-amber-950">
            가입 당시 알린 내용도 확인해두세요
          </p>
          <p className="mt-1 text-xs leading-5 text-amber-900/80">
            청구 심사에서는 가입 당시 청약서에 답한 내용과 약관을 확인할 수
            있어요. 고지 대상과 질문 기간은 계약마다 다르므로, 기억에만 의존하지
            말고 청약서 원문을 기준으로 살펴보세요.
          </p>
        </div>
      </div>
    </section>
  );
}

function ChannelLinkList({
  links,
  className,
}: {
  links: ClaimChannelBlock["insurers"][number]["links"];
  className?: string;
}) {
  if (!links.length) return null;

  return (
    <div className={className}>
      <div className="flex flex-wrap gap-2">
        {links.map((link) => {
          const href = safeHref(link.url);
          if (!href) {
            return (
              <span
                key={`${link.label}-${link.url}`}
                className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-medium text-zinc-500"
              >
                {link.label}
              </span>
            );
          }

          return (
            <a
              key={`${link.label}-${link.url}`}
              href={href}
              target="_blank"
              rel="noreferrer"
              className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-blue-700 ring-1 ring-blue-200"
            >
              {link.label}
            </a>
          );
        })}
      </div>
    </div>
  );
}

function AnalysisLoading() {
  return (
    <section
      aria-live="polite"
      aria-busy="true"
      className="rounded-2xl border border-zinc-200 p-8"
    >
      <div className="h-2 w-20 animate-pulse rounded bg-blue-600" />
      <h2 className="mt-5 text-xl font-semibold">
        전체 보험의 핵심 보장을 확인하고 있어요
      </h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">
        사망·3대 진단비·실손의료비와 보험 종류별 담보를 정리하고 있어요.
      </p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((item) => (
          <div
            key={item}
            className="h-40 animate-pulse rounded-xl bg-zinc-100"
          />
        ))}
      </div>
    </section>
  );
}

function InfoState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 p-8 text-center">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-zinc-500">
        {description}
      </p>
    </section>
  );
}
