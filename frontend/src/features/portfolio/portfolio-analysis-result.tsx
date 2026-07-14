import type { CSSProperties } from "react";
import { formatWon } from "./money-format";
import type {
  AnalysisEvidence,
  PortfolioAnalysisResult,
} from "./portfolio-api";

type ReviewDisplayItem = {
  title: string;
  detail?: string;
  evidence_ids?: string[];
};

export function PortfolioAnalysisResultView({
  result,
  insuredName,
}: {
  result: PortfolioAnalysisResult;
  insuredName?: string;
}) {
  const strengths =
    result.counselor?.strengths ??
    result.prepared_coverages.map((title) => ({ title }));
  const rawGaps =
    result.counselor?.gaps ??
    result.coverage_gaps.map((item) => ({
      title: item.category,
      detail: item.reason,
    }));
  const gaps = rawGaps.filter((item) => !isExcludedDataLimitReviewItem(item));
  const analyzedTitles = (result.sources ?? []).map(
    (source) => source.product_name || source.insurer || "이름 미확인",
  );
  const limitations = [
    ...(result.limitations ?? []),
    ...result.notices,
    result.baseline_notice,
  ].filter(Boolean);
  const evidenceById = new Map<string, AnalysisEvidence>();
  for (const evidence of result.evidence ?? []) {
    if (evidence.id) evidenceById.set(evidence.id, evidence);
  }
  const overview =
    result.counselor?.overview ??
    `${result.life_stage} 기준으로 보험 ${result.policy_count}건에서 확인 가능한 보장을 정리했어요.`;
  const priorityChecks = result.priority_checks ?? [];
  const claimConditionChecks = result.claim_condition_checks ?? [];
  const policyChangeChecks = result.policy_change_checks ?? [];

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-blue-100 bg-blue-50/50 p-6 sm:p-8">
        <p className="text-xs font-semibold tracking-[0.12em] text-blue-700 uppercase">
          AI 보험 상담
        </p>
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-2xl font-semibold tracking-[-0.04em]">
            Coverly AI가 {insuredName ? `${insuredName}님` : "당신"} 편에서
            살펴봤어요
          </h2>
          <span className="text-xs text-zinc-500">
            {result.age === null ? "나이 미확인" : `${result.age}세`} ·{" "}
            {result.gender} · {result.life_stage}
          </span>
        </div>
        <dl className="mt-6 grid gap-3 sm:grid-cols-3">
          <Metric
            label="중복된 보장"
            value={`${result.indemnity_duplicate_count}개`}
          />
          <Metric label="보장 공백" value={`${gaps.length}개`} />
          <Metric
            label="매달 내는 보험료"
            value={formatWon(result.premium.monthly_total)}
          />
        </dl>
      </section>

      <AnalysisSummary overview={overview} />

      <PremiumPosition result={result} />

      {priorityChecks.length ? (
        <PriorityChecks items={priorityChecks} evidenceById={evidenceById} />
      ) : null}

      {result.coverage_amount_status ? (
        <CoverageAmountStatusSection
          status={result.coverage_amount_status}
          evidenceById={evidenceById}
        />
      ) : null}

      {analyzedTitles.length ? (
        <section className="rounded-2xl border border-zinc-200 p-6">
          <h2 className="text-sm font-semibold">이번 분석에 사용한 보험</h2>
          <ul className="mt-3 space-y-2 text-sm text-zinc-700">
            {analyzedTitles.map((title, index) => (
              <li
                key={`${title}-${index}`}
                className="rounded-lg bg-zinc-50 px-3 py-2"
              >
                {title}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.indemnity_duplicate_count > 0 ? (
        <section className="rounded-2xl border border-blue-100 bg-blue-50/40 px-5 py-4">
          <p className="text-sm font-medium text-blue-900">
            중복 수령이 안 되는데 겹쳐 가입된 보장{" "}
            {result.indemnity_duplicate_count}건
          </p>
          <p className="mt-1 text-xs leading-5 text-blue-700">
            같은 실손·비례보상 보장은 여러 개 들어도 더 받지 못해요. 정리하면
            보험료를 아낄 수 있어요.
          </p>
        </section>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-2">
        <ReviewCard
          eyebrow="확인된 보장"
          title="증권에서 확인된 부분"
          items={strengths}
          evidenceById={evidenceById}
          empty="현재 데이터에서 설명할 수 있는 보장을 확인하지 못했어요."
          reasonLabel="왜 의미가 있나요?"
        />
        <ReviewCard
          eyebrow="추가 확인"
          title="다른 자료도 확인할 부분"
          items={gaps}
          evidenceById={evidenceById}
          empty="현재 자료에서 추가로 확인할 항목을 찾지 못했어요."
          tone="warning"
          reasonLabel="왜 확인하나요?"
        />
      </div>

      <ReviewCard
        eyebrow="다음 단계"
        title="이어서 확인하면 좋아요"
        items={(result.counselor?.next_steps ?? []).map((title) => ({
          title,
        }))}
        evidenceById={evidenceById}
        empty="원본 약관과 최신 계약 상태도 함께 확인해보세요."
      />

      {claimConditionChecks.length || policyChangeChecks.length ? (
        <AnalysisDetailGrid
          claimConditionChecks={claimConditionChecks}
          policyChangeChecks={policyChangeChecks}
          evidenceById={evidenceById}
        />
      ) : null}

      <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
        <h2 className="text-sm font-semibold">확인 범위와 한계</h2>
        <ul className="mt-3 space-y-2 text-xs leading-5 text-zinc-500">
          <li className="font-medium text-zinc-700">
            · Coverly AI는 보험을 팔지 않아요. 겹치거나 불필요한 보장을 먼저
            알려드려요.
          </li>
          {limitations.map((item, index) => (
            <li key={`${item}-${index}`}>· {item}</li>
          ))}
          <li>· 자동차보험은 이번 분석에서 제외했어요.</li>
        </ul>
      </section>
    </div>
  );
}

function AnalysisSummary({ overview }: { overview: string }) {
  return (
    <section className="border-y border-zinc-200 py-6">
      <p className="text-xs font-semibold text-blue-700">총평</p>
      <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
        보험을 한데 모아 보면
      </h2>
      <p className="mt-3 max-w-4xl text-sm leading-7 text-zinc-700">
        {overview}
      </p>
    </section>
  );
}

function PremiumPosition({ result }: { result: PortfolioAnalysisResult }) {
  const monthlyPremium = result.premium.monthly_total;
  const benchmark = result.premium_benchmark;
  if (
    typeof monthlyPremium !== "number" ||
    result.premium.monthly_policy_count < 1 ||
    !benchmark
  ) {
    return null;
  }

  const maxAmount =
    Math.max(monthlyPremium, benchmark.average_monthly_premium) * 1.35;
  const userPosition = progressPosition(monthlyPremium, maxAmount);
  const benchmarkPosition = progressPosition(
    benchmark.average_monthly_premium,
    maxAmount,
  );
  const difference = monthlyPremium - benchmark.average_monthly_premium;
  const comparison =
    Math.abs(difference) < 10_000
      ? "평균과 거의 비슷해요"
      : difference > 0
        ? "평균보다 높게 내고 있어요"
        : "평균보다 낮게 내고 있어요";
  const style = {
    "--premium-position": `${userPosition}%`,
  } as CSSProperties;

  return (
    <section className="rounded-2xl border border-zinc-200 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-blue-700">내 보험료 위치</p>
          <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
            {benchmark.age_band_label} 평균과 비교하면
          </h2>
        </div>
        <p className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-600">
          {comparison}
        </p>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <Metric label="내 월 보험료" value={formatWon(monthlyPremium)} />
        <Metric
          label={`${benchmark.age_band_label} 평균`}
          value={formatWon(benchmark.average_monthly_premium)}
        />
      </div>

      <div className="mt-7">
        <div className="relative h-12" style={style}>
          <div className="absolute inset-x-0 top-5 h-2 rounded-full bg-zinc-100" />
          <div className="premium-position-fill absolute top-5 left-0 h-2 rounded-full bg-blue-600" />
          <div
            className="absolute top-1 flex -translate-x-1/2 flex-col items-center gap-1"
            style={{ left: `${benchmarkPosition}%` }}
          >
            <span className="text-xs font-medium text-zinc-500">평균</span>
            <span className="h-0 w-0 border-x-[5px] border-t-[7px] border-x-transparent border-t-zinc-500" />
          </div>
          <div className="premium-position-user absolute top-3 flex -translate-x-1/2 flex-col items-center gap-1">
            <span className="h-4 w-4 rounded-full border-2 border-white bg-blue-600 shadow-sm" />
            <span className="text-xs font-semibold text-blue-700">나</span>
          </div>
        </div>
        <div className="mt-1 flex justify-between text-xs text-zinc-400">
          <span>낮음</span>
          <span>높음</span>
        </div>
      </div>

      <p className="mt-4 text-xs leading-5 text-zinc-500">
        {benchmark.source.label} 기준이에요. {benchmark.source.caveat}
      </p>
    </section>
  );
}

function PriorityChecks({
  items,
  evidenceById,
}: {
  items: ReviewDisplayItem[];
  evidenceById: Map<string, AnalysisEvidence>;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 p-6">
      <p className="text-xs font-semibold text-blue-700">우선 확인 3가지</p>
      <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
        지금 화면에서 먼저 볼 부분
      </h2>
      <ol className="mt-4 space-y-3">
        {items.slice(0, 3).map((item, index) => (
          <li
            key={`${item.title}-${index}`}
            className="flex gap-3 rounded-xl bg-zinc-50 px-4 py-3 text-sm"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
              {index + 1}
            </span>
            <div>
              <p className="font-medium text-zinc-800">{item.title}</p>
              {item.detail ? (
                <p className="mt-2 leading-6 text-zinc-500">{item.detail}</p>
              ) : null}
              <EvidenceDetails
                evidenceIds={item.evidence_ids}
                evidenceById={evidenceById}
              />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CoverageAmountStatusSection({
  status,
  evidenceById,
}: {
  status: NonNullable<PortfolioAnalysisResult["coverage_amount_status"]>;
  evidenceById: Map<string, AnalysisEvidence>;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-blue-700">보장금액 상태</p>
          <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
            {status.title}
          </h2>
        </div>
        <p className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-600">
          총 {formatWon(status.confirmed_total_amount)}
        </p>
      </div>
      <p className="mt-3 text-sm leading-6 text-zinc-500">{status.detail}</p>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Metric
          label="금액 확인 항목"
          value={`${status.confirmed_category_count}개`}
        />
        <Metric
          label="확인된 합계"
          value={formatWon(status.confirmed_total_amount)}
        />
        <Metric
          label="금액 미확인"
          value={`${status.unconfirmed_coverage_count}개`}
        />
      </div>

      {status.items.length ? (
        <ul className="mt-4 space-y-3">
          {status.items.map((item) => (
            <li
              key={item.title}
              className="rounded-xl bg-zinc-50 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-medium text-zinc-800">{item.title}</p>
                <span className="text-xs text-zinc-500">
                  {item.coverage_count}개 담보
                </span>
              </div>
              <p className="mt-2 leading-6 text-zinc-500">{item.detail}</p>
              <EvidenceDetails
                evidenceIds={item.evidence_ids}
                evidenceById={evidenceById}
              />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function AnalysisDetailGrid({
  claimConditionChecks,
  policyChangeChecks,
  evidenceById,
}: {
  claimConditionChecks: NonNullable<
    PortfolioAnalysisResult["claim_condition_checks"]
  >;
  policyChangeChecks: NonNullable<
    PortfolioAnalysisResult["policy_change_checks"]
  >;
  evidenceById: Map<string, AnalysisEvidence>;
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {claimConditionChecks.length ? (
        <section className="rounded-2xl border border-zinc-200 p-6">
          <p className="text-xs font-semibold text-blue-700">
            받을 때 확인할 조건
          </p>
          <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
            보험금은 약관 조건을 통과해야 해요
          </h2>
          <ul className="mt-4 space-y-3">
            {claimConditionChecks.map((item) => (
              <li
                key={item.title}
                className="rounded-xl bg-zinc-50 px-4 py-3 text-sm"
              >
                <p className="font-medium text-zinc-800">{item.title}</p>
                <p className="mt-2 leading-6 text-zinc-500">{item.detail}</p>
                <EvidenceDetails
                  evidenceIds={item.evidence_ids}
                  evidenceById={evidenceById}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {policyChangeChecks.length ? (
        <section className="rounded-2xl border border-zinc-200 p-6">
          <p className="text-xs font-semibold text-blue-700">최근 제도 변화</p>
          <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
            내 보험과 연결해서 볼 변화
          </h2>
          <ul className="mt-4 space-y-3">
            {policyChangeChecks.map((item) => (
              <li
                key={item.title}
                className="rounded-xl bg-zinc-50 px-4 py-3 text-sm"
              >
                <p className="font-medium text-zinc-800">{item.title}</p>
                <p className="mt-2 leading-6 text-zinc-500">{item.summary}</p>
                <p className="mt-2 leading-6 text-zinc-600">
                  {item.user_impact}
                </p>
                <p className="mt-3 text-xs leading-5 text-zinc-500">
                  {item.source.label} 기준이에요. {item.source.caveat}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function ReviewCard({
  eyebrow,
  title,
  items,
  evidenceById,
  empty,
  tone = "default",
  reasonLabel,
}: {
  eyebrow: string;
  title: string;
  items: ReviewDisplayItem[];
  evidenceById: Map<string, AnalysisEvidence>;
  empty: string;
  tone?: "default" | "warning";
  reasonLabel?: string;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 p-6">
      <p
        className={`text-xs font-semibold ${tone === "warning" ? "text-amber-700" : "text-blue-700"}`}
      >
        {eyebrow}
      </p>
      <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">{title}</h2>
      {items.length ? (
        <ul className="mt-4 space-y-3">
          {items.map((item, index) => (
            <li
              key={`${item.title}-${index}`}
              className="rounded-xl bg-zinc-50 px-4 py-3 text-sm"
            >
              <p className="font-medium text-zinc-800">{item.title}</p>
              {item.detail ? (
                <p className="mt-2 leading-6 text-zinc-500">
                  {reasonLabel ? (
                    <strong className="font-semibold text-zinc-700">
                      {reasonLabel}{" "}
                    </strong>
                  ) : null}
                  {item.detail}
                </p>
              ) : null}
              <EvidenceDetails
                evidenceIds={item.evidence_ids}
                evidenceById={evidenceById}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm leading-6 text-zinc-500">{empty}</p>
      )}
    </section>
  );
}

function EvidenceDetails({
  evidenceIds = [],
  evidenceById,
}: {
  evidenceIds?: string[];
  evidenceById: Map<string, AnalysisEvidence>;
}) {
  const evidence = evidenceIds.flatMap((id) => {
    const item = evidenceById.get(id);
    return item ? [item] : [];
  });
  if (!evidence.length) return null;

  return (
    <details className="mt-3 border-t border-zinc-200 pt-3">
      <summary className="cursor-pointer text-xs font-medium text-blue-700">
        근거 보기
      </summary>
      <ul className="mt-2 space-y-2 text-xs leading-5 text-zinc-500">
        {evidence.map((item, index) => (
          <li key={`${item.id ?? "evidence"}-${index}`}>
            {plainEvidenceSummary(item)}
          </li>
        ))}
      </ul>
    </details>
  );
}

function isExcludedDataLimitReviewItem(item: ReviewDisplayItem) {
  if (item.evidence_ids?.some((id) => id.startsWith("excluded:"))) return true;
  const text = `${item.title} ${item.detail ?? ""}`;
  return text.includes("지급 방식") || text.includes("지급유형");
}

function plainEvidenceSummary(evidence: AnalysisEvidence) {
  const id = evidence.id ?? "";
  if (id.startsWith("official:")) {
    const publisher = evidence.publisher || "공식기관";
    const source = evidence.source_title || "공식자료";
    const citation = evidence.citation_label
      ? ` ${evidence.citation_label}`
      : "";
    return `${publisher}의 ${source}${citation}를 참고했어요.`;
  }

  if (id.startsWith("gap:")) {
    const coverage = evidence.coverage_name || "이 항목";
    return `올린 비자동차 보험 전체에서 ${coverage} 담보를 찾지 못했어요.`;
  }

  if (id.startsWith("excluded:")) {
    const coverage = evidence.coverage_name || "이 담보";
    return `${coverage}은 금액이나 지급 방식을 확인하기 어려워 따로 살펴봤어요.`;
  }

  const source = evidence.product_name || evidence.insurer || "올린 증권";
  const coverage = evidence.coverage_name || "해당 담보";
  if (evidence.amount !== undefined) {
    return `${source}에서 ${coverage} 가입금액 ${formatWon(evidence.amount)}을 확인했어요.`;
  }
  return `${source}에서 ${coverage} 가입 사실을 확인했어요.`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white bg-white px-4 py-4">
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-2 font-semibold text-zinc-900">{value}</dd>
    </div>
  );
}

function progressPosition(amount: number, maxAmount: number) {
  if (maxAmount <= 0) return 0;
  return Math.min(96, Math.max(4, (amount / maxAmount) * 100));
}
