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
  const gaps =
    result.counselor?.gaps ??
    result.coverage_gaps.map((item) => ({
      title: item.category,
      detail: item.reason,
    }));
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
