import type { CSSProperties, ReactNode } from "react";

import { primaryButtonClassName } from "../../components/coverly-brand";
import type { EmptyReason } from "./analysis-eligibility";
import { formatKoreanWon, formatWon } from "./money-format";
import type {
  ClaimChannelBlock,
  EssentialCoverageItem,
  PortfolioSummary,
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
    rangeLabel: "기본 장례비 기준",
    rangeNote:
      "1인 가구 기준으로는 장례비 1,000만~2,000만원 정도부터 보고, 부양가족이 있으면 생활비까지 따로 봐야 해요.",
  },
  diagnosis: {
    title: "3대 진단보험",
    description:
      "암, 뇌혈관질환, 심장질환처럼 치료비와 소득 공백이 크게 생길 수 있는 병을 대비해요.",
    rangeLabel: "민간 가이드 기준",
    rangeNote:
      "민간 가이드에서는 암·뇌혈관은 3,000만원 안팎부터, 심장은 2,000만~3,000만원부터 먼저 보는 편이에요.",
  },
  indemnity: {
    title: "실손의료보험",
    description:
      "입원·통원처럼 자주 생기는 의료비 중 실제로 쓴 돈을 약관 한도 안에서 돌려받는 보험이에요.",
    rangeLabel: "금액보다 구조 확인",
    rangeNote:
      "실손은 가입금액 합계보다 가입 여부, 세대, 자기부담금, 중복 여부가 더 중요해요.",
  },
} as const;

export function PortfolioAnalysisPanel({
  status,
  summary,
  eligibleCount,
  emptyReason,
  onRetry,
}: {
  status: "loading" | "success" | "error";
  summary?: PortfolioSummary;
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
  const missingItems = items.filter((item) => item.status === "not_found");
  const reviewItems = items.filter((item) => item.status === "needs_review");

  return (
    <div className="space-y-8">
      <PortfolioOverview
        summary={summary}
        items={items}
        policyCount={eligibleCount}
        missingItems={missingItems}
        reviewItems={reviewItems}
        specialAnalyses={specialAnalyses}
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
  policyCount,
  missingItems,
  reviewItems,
  specialAnalyses,
}: {
  summary?: PortfolioSummary;
  items: EssentialCoverageItem[];
  policyCount: number;
  missingItems: EssentialCoverageItem[];
  reviewItems: EssentialCoverageItem[];
  specialAnalyses: SpecialPolicyAnalysis[];
}) {
  const confirmedItems = items.filter((item) => item.status !== "not_found");
  const diagnosisItems = items.filter((item) => DIAGNOSIS_KINDS.has(item.kind));
  const confirmedDiagnosisCount = diagnosisItems.filter(
    (item) => item.status !== "not_found",
  ).length;
  const premium = summary?.premium ?? null;
  const premiumBenchmark = summary?.premium_benchmark ?? null;
  const premiumComparison = premiumSummaryComparison(premium, premiumBenchmark);
  const generatedOverview = summary?.overview ?? null;
  const fallbackTitle = overallTitle(
    confirmedItems,
    missingItems,
    premiumComparison,
  );
  const fallbackParagraphs = overallNarrativeParagraphs(
    confirmedItems,
    missingItems,
    reviewItems,
    premium,
    premiumBenchmark,
  );
  const fallbackTakeaways = overallTakeaways(
    confirmedItems,
    missingItems,
    reviewItems,
    premium,
    premiumBenchmark,
    premiumComparison,
  );
  const overviewTitle = generatedOverview?.title || fallbackTitle;
  const narrativeParagraphs = generatedOverview?.paragraphs.length
    ? generatedOverview.paragraphs
    : fallbackParagraphs;
  const takeaways = generatedOverview?.takeaways.length
    ? generatedOverview.takeaways
    : fallbackTakeaways;

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
              {overviewTitle}
            </h2>
            <div className="mt-4 max-w-3xl space-y-3 text-sm leading-7 text-pretty text-zinc-300">
              {narrativeParagraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>

            <div className="mt-6 grid gap-3 border-y border-white/10 py-4 text-sm sm:grid-cols-3">
              {takeaways.map((takeaway) => (
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

      <RecommendedInsuranceCards items={items} />
    </section>
  );
}

function RecommendedInsuranceCards({
  items,
}: {
  items: EssentialCoverageItem[];
}) {
  const death = items.find((item) => item.kind === "death");
  const diagnosisItems = items.filter((item) => DIAGNOSIS_KINDS.has(item.kind));
  const indemnity = items.find((item) => item.kind === "indemnity");
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
        />

        <RecommendedDiagnosisCard
          items={diagnosisItems}
          confirmedCount={diagnosisConfirmedCount}
        />

        <RecommendedIndemnityCard item={indemnity} />
      </div>
    </article>
  );
}

function overallTitle(
  confirmedItems: EssentialCoverageItem[],
  missingItems: EssentialCoverageItem[],
  premiumComparison:
    ReturnType<typeof premiumSummaryComparison> | null | undefined,
) {
  const hasMissingDiagnosis = missingItems.some((item) =>
    DIAGNOSIS_KINDS.has(item.kind),
  );

  if (premiumComparison?.tone === "low" && hasMissingDiagnosis) {
    return "보험료는 낮지만, 진단비 공백을 먼저 확인해야 해요";
  }
  if (premiumComparison?.tone === "low") {
    return "보험료는 권장 범위보다 낮고, 보장 구성을 함께 봐야 해요";
  }
  if (premiumComparison?.tone === "high" && missingItems.length > 0) {
    return "보험료는 높은데, 현재 자료에서 비어 보이는 보장이 있어요";
  }
  if (premiumComparison?.tone === "high") {
    return "보험료가 높은 편이라 보장 효율을 먼저 봐야 해요";
  }
  if (premiumComparison?.tone === "in_range" && missingItems.length > 0) {
    return "보험료는 권장 범위 안이고, 빠진 보장을 이어서 확인해요";
  }
  if (premiumComparison?.tone === "in_range") {
    return "보험료와 핵심 보장이 비교적 균형 있게 보여요";
  }
  if (confirmedItems.length >= 3 && missingItems.length > 0) {
    return "기본 축은 보이지만, 비어 보이는 보장이 있어요";
  }
  if (confirmedItems.length > 0) {
    return "확인된 가입과 미확인 보장이 함께 보여요";
  }
  return "현재 자료에서는 핵심 보장 가입을 확인하지 못했어요";
}

function overallNarrativeParagraphs(
  confirmedItems: EssentialCoverageItem[],
  missingItems: EssentialCoverageItem[],
  reviewItems: EssentialCoverageItem[],
  premium: PortfolioSummary["premium"] | null | undefined,
  benchmark: PortfolioSummary["premium_benchmark"] | null | undefined,
) {
  return [
    premiumSummaryNarrative(premium, benchmark),
    coverageSummaryNarrative(confirmedItems, missingItems, reviewItems),
    "이 총평은 업로드한 증권에서 읽은 담보명, 가입금액, 월 보험료를 기준으로 만든 1차 해석이에요. 실제 충분성은 피보험자 소득, 부양가족, 대출, 기존 병력, 약관의 면책·감액·갱신 조건까지 같이 봐야 해요.",
  ].filter(Boolean);
}

function coverageSummaryNarrative(
  confirmedItems: EssentialCoverageItem[],
  missingItems: EssentialCoverageItem[],
  reviewItems: EssentialCoverageItem[],
) {
  if (confirmedItems.length === 0) {
    return `${itemLabels(missingItems, "사망·3대 진단비·실손")} 항목은 현재 올린 자료에서 찾지 못했어요. 다른 증권이나 특약명에 숨어 있는지는 추가 확인이 필요해요.`;
  }

  const confirmedText = itemLabels(confirmedItems, "");
  if (missingItems.length === 0) {
    const reviewText =
      reviewItems.length > 0
        ? ` 다만 ${itemLabels(reviewItems, "")}은 중복 가능성을 따로 봐야 해요.`
        : "";
    return `${confirmedText} 항목은 현재 자료에서 확인돼요.${reviewText} 가입금액이 충분한지와 지급 조건은 각 증권의 약관으로 한 번 더 확인해야 해요.`;
  }

  return `${confirmedText} 항목은 확인됐지만, ${itemLabels(missingItems, "")} 항목은 현재 올린 자료에서 찾지 못했어요. 특히 3대 진단비는 암·뇌혈관·심장질환을 함께 봐야 해서 빠진 축을 먼저 확인하는 게 좋아요.`;
}

function overallTakeaways(
  confirmedItems: EssentialCoverageItem[],
  missingItems: EssentialCoverageItem[],
  reviewItems: EssentialCoverageItem[],
  premium: PortfolioSummary["premium"] | null | undefined,
  benchmark: PortfolioSummary["premium_benchmark"] | null | undefined,
  premiumComparison:
    ReturnType<typeof premiumSummaryComparison> | null | undefined,
) {
  return [
    {
      label: "보험료",
      title: premiumComparison?.label ?? "보험료 확인 필요",
      detail: premiumTakeawayDetail(premium, benchmark),
    },
    {
      label: "보장 구성",
      title: `${confirmedItems.length}/5개 확인`,
      detail:
        missingItems.length > 0
          ? `${itemLabels(missingItems, "")} 항목은 현재 자료에서 미확인이에요.`
          : "사망·3대 진단비·실손 축이 모두 보여요.",
    },
    {
      label: "다음 확인",
      title:
        reviewItems.length > 0
          ? "중복 여부 확인"
          : missingItems.length > 0
            ? "미확인 보장 확인"
            : "약관 조건 확인",
      detail:
        reviewItems.length > 0
          ? `${itemLabels(reviewItems, "")}의 중복 가입과 실제 보장 범위를 확인해요.`
          : missingItems.length > 0
            ? "다른 증권, 특약명, 가입설계서에 빠진 보장이 있는지 봐요."
            : "면책, 감액, 갱신, 자기부담금 조건을 약관에서 확인해요.",
    },
  ];
}

function premiumTakeawayDetail(
  premium: PortfolioSummary["premium"] | null | undefined,
  benchmark: PortfolioSummary["premium_benchmark"] | null | undefined,
) {
  if (!premium || typeof premium.monthly_total !== "number") {
    return "월 보험료 자료가 부족해 적정성을 판단하기 어려워요.";
  }
  if (!benchmark || premium.monthly_policy_count < 1) {
    return `${formatWon(premium.monthly_total)}만 현재 자료에서 확인돼요.`;
  }
  return `${formatWon(premium.monthly_total)} / 권장 ${formatWon(benchmark.suggested_min_premium)}~${formatWon(benchmark.suggested_max_premium)}`;
}

function itemLabels(items: EssentialCoverageItem[], emptyCopy: string) {
  if (items.length === 0) return emptyCopy;
  return items.map((item) => item.label).join(" · ");
}

function RecommendedSingleCoverageCard({
  eyebrow,
  item,
  copy,
}: {
  eyebrow: string;
  item: EssentialCoverageItem | undefined;
  copy: typeof RECOMMENDED_INSURANCE_COPY.death;
}) {
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

      <div className="mt-5">
        <CoverageAmountMeter
          item={item}
          rangeLabel={copy.rangeLabel}
          fallbackNote={copy.rangeNote}
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
          <li
            key={item.kind}
            className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-zinc-950">
                  {item.label}
                </p>
                <p className="mt-1 text-xs leading-5 text-zinc-500">
                  {item.detail}
                </p>
              </div>
              <CoverageStatusBadge status={item.status} />
            </div>

            <div className="mt-3">
              <CoverageAmountMeter
                item={item}
                rangeLabel={RECOMMENDED_INSURANCE_COPY.diagnosis.rangeLabel}
                fallbackNote={RECOMMENDED_INSURANCE_COPY.diagnosis.rangeNote}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RecommendedIndemnityCard({
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
            {RECOMMENDED_INSURANCE_COPY.indemnity.title}
          </h4>
        </div>
        <CoverageStatusBadge status={item?.status ?? "not_found"} />
      </div>

      <p className="mt-4 text-sm leading-6 text-zinc-700">
        {RECOMMENDED_INSURANCE_COPY.indemnity.description}
      </p>

      <div className="mt-5 rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
        <p className="text-xs font-semibold text-zinc-500">현재 확인 결과</p>
        <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-zinc-950">
          {indemnityHeadline(item)}
        </p>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          {item?.detail ?? "현재 자료에서 가입 여부를 확인하지 못했어요."}
        </p>
      </div>

      <div className="mt-4 rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold text-zinc-500">
          {RECOMMENDED_INSURANCE_COPY.indemnity.rangeLabel}
        </p>
        <p className="mt-1 text-sm leading-6 text-zinc-700">
          {RECOMMENDED_INSURANCE_COPY.indemnity.rangeNote}
        </p>
      </div>

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

  if (minAmount == null || maxAmount == null) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-3">
        <p className="text-xs font-semibold text-zinc-500">{rangeLabel}</p>
        <p className="mt-1 text-sm leading-6 text-zinc-700">{fallbackNote}</p>
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
            {formatKoreanWon(minAmount)}
            {minAmount !== maxAmount ? ` ~ ${formatKoreanWon(maxAmount)}` : ""}
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

      <p className="mt-3 text-xs leading-5 text-zinc-500">{fallbackNote}</p>
    </div>
  );
}

function indemnityHeadline(item: EssentialCoverageItem | undefined) {
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
        비교했어요. 민간 가이드 기준이에요.
      </p>
    </div>
  );
}

function premiumSummaryComparison(
  premium: PortfolioSummary["premium"] | null | undefined,
  benchmark: PortfolioSummary["premium_benchmark"] | null | undefined,
) {
  if (
    !premium ||
    !benchmark ||
    typeof premium.monthly_total !== "number" ||
    premium.monthly_policy_count < 1
  ) {
    return null;
  }

  if (premium.monthly_total < benchmark.suggested_min_premium) {
    return {
      tone: "low" as const,
      label: "권장 범위보다 낮아요",
      title: "월 보험료가 권장 범위보다 낮아요",
    };
  }
  if (premium.monthly_total > benchmark.suggested_max_premium) {
    return {
      tone: "high" as const,
      label: "권장 범위보다 높아요",
      title: "월 보험료가 권장 범위보다 높아요",
    };
  }
  return {
    tone: "in_range" as const,
    label: "권장 범위 안에 있어요",
    title: "월 보험료가 권장 범위 안에 있어요",
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

function premiumSummaryNarrative(
  premium: PortfolioSummary["premium"] | null | undefined,
  benchmark: PortfolioSummary["premium_benchmark"] | null | undefined,
) {
  const comparison = premiumSummaryComparison(premium, benchmark);
  if (!premium || typeof premium.monthly_total !== "number") {
    return "";
  }
  if (!comparison || !benchmark || premium.monthly_policy_count < 1) {
    return `월납으로 확인된 보험료는 ${formatWon(premium.monthly_total)}이에요.`;
  }

  const rangeText = `${benchmark.age_band_label} 평균 소득 기준 권장 범위 ${formatWon(benchmark.suggested_min_premium)}~${formatWon(benchmark.suggested_max_premium)}`;
  if (comparison.tone === "low") {
    return `월납으로 확인된 보험료는 ${formatWon(premium.monthly_total)}으로, ${rangeText}보다 낮아요. 보험료가 낮은 것 자체가 문제는 아니지만, 필요한 보장이 빠져서 낮게 보이는지 먼저 확인해야 해요.`;
  }
  if (comparison.tone === "high") {
    return `월납으로 확인된 보험료는 ${formatWon(premium.monthly_total)}으로, ${rangeText}보다 높아요. 이 경우에는 보장이 충분해서 높은 건지, 중복 담보나 갱신형 보험료 때문에 부담이 커진 건지 나눠서 봐야 해요.`;
  }
  return `월납으로 확인된 보험료는 ${formatWon(premium.monthly_total)}으로, ${rangeText} 안에 있어요. 다만 권장 범위 안이라는 말이 보장이 충분하다는 뜻은 아니어서, 빠진 보장과 지급 조건을 함께 봐야 해요.`;
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
        "공통으로 청구서와 신분증을 준비해요. 진단비는 진단서, 실손은 진료비 계산서·영수증과 세부내역서가 기본이에요.",
    },
    {
      title: "청구 채널 선택",
      description:
        "실손은 실손24와 보험사 채널 중에서 고를 수 있어요. 그 외 보험금은 보험사 앱·홈페이지·우편·방문 중 가능한 방법으로 접수해요.",
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
                  {index === 2 && claimChannels?.indemnity ? (
                    <div className="mt-3 space-y-3">
                      <div className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2.5 text-xs leading-5 text-zinc-600">
                        <p className="font-semibold text-zinc-900">
                          {claimChannels.indemnity.name}
                        </p>
                        {claimChannels.indemnity.description ? (
                          <p className="mt-1">
                            {claimChannels.indemnity.description}
                          </p>
                        ) : null}
                        <p className="mt-1">
                          참여 병원이라면 진료비 서류를 전자 전송할 수 있어요.
                          먼저 연계 병원인지 확인해요.
                        </p>
                        {claimChannels.indemnity.call_center ? (
                          <p className="mt-1 text-zinc-500">
                            콜센터 {claimChannels.indemnity.call_center}
                          </p>
                        ) : null}
                        <ChannelLinkList
                          links={claimChannels.indemnity.links}
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
                                실손도 보험사 앱이나 홈페이지에서 직접 청구할 수
                                있어요.
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
        사망·3대 진단비·실손과 보험 종류별 담보를 정리하고 있어요.
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
