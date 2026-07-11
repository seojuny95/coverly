import type {
  AmountReviewItem,
  PortfolioAnalysisResult,
} from "./portfolio-api";

export function PortfolioAnalysisResultView({
  result,
}: {
  result: PortfolioAnalysisResult;
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
  const amountReviewItems = result.counselor?.amount_review_items ?? [];
  const limitations = [
    ...(result.limitations ?? []),
    ...result.notices,
    result.baseline_notice,
  ].filter(Boolean);

  return (
    <div className="space-y-5">
      {result.status === "partial" ? (
        <p
          role="status"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          일부 보험은 확인하지 못했어요. 확인된 내용부터 보여드려요.
        </p>
      ) : null}

      <section className="rounded-2xl border border-blue-100 bg-blue-50/50 p-6 sm:p-8">
        <p className="text-xs font-semibold tracking-[0.12em] text-blue-700 uppercase">
          내 보험 상담
        </p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em]">
          Coverly가 당신 편에서 살펴봤어요
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-zinc-600">
          {result.counselor?.overview ??
            `${result.life_stage} 기준으로 보험 ${result.policy_count}건에서 확인 가능한 보장을 정리했어요.`}
        </p>
        <p className="mt-4 text-xs text-zinc-500">
          {result.age === null ? "나이 미확인" : `${result.age}세`} ·{" "}
          {result.gender} · {result.life_stage}
        </p>
        <dl className="mt-6 grid gap-3 sm:grid-cols-3">
          <Metric label="살펴본 보험" value={`${result.policy_count}개`} />
          <Metric
            label="확인한 정액 보장"
            value={`${result.confirmed_total_count}개`}
          />
          <Metric
            label="확인한 보험금 합계"
            value={formatWon(result.confirmed_total_amount)}
          />
        </dl>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <ReviewCard
          eyebrow="현재 강점"
          title="증권에서 확인한 준비 항목"
          items={strengths}
          empty="현재 데이터에서 뚜렷한 준비 항목을 확인하지 못했어요."
        />
        <ReviewCard
          eyebrow="보장 공백"
          title="더 확인해볼 항목"
          items={gaps}
          empty="일반 확인 기준에서 빠진 항목을 찾지 못했어요."
          tone="warning"
        />
      </div>

      <AmountReviewCard items={amountReviewItems} />

      <div className="grid gap-5 lg:grid-cols-2">
        <ReviewCard
          eyebrow="다음 질문"
          title="함께 생각해볼 질문"
          items={(result.counselor?.next_questions ?? []).map((title) => ({
            title,
          }))}
          empty="보험금이 필요한 상황과 월 납입 여력을 먼저 정리해보세요."
        />
        <ReviewCard
          eyebrow="다음 단계"
          title="이어서 확인하면 좋아요"
          items={(result.counselor?.next_steps ?? []).map((title) => ({
            title,
          }))}
          empty="원본 약관과 최신 계약 상태도 함께 확인해보세요."
        />
      </div>

      {result.evidence?.length ? (
        <section className="rounded-2xl border border-zinc-200 p-6">
          <h2 className="font-semibold">판단에 사용한 근거</h2>
          <ul className="mt-4 divide-y divide-zinc-100 text-sm">
            {result.evidence.map((item, index) => (
              <li
                key={item.id ?? `${item.label ?? item.fact}-${index}`}
                className="py-3 first:pt-0"
              >
                <p className="font-medium text-zinc-800">
                  {item.label ??
                    ([item.insurer, item.product_name, item.coverage_name]
                      .filter(Boolean)
                      .join(" · ") ||
                      "증권에서 확인한 내용")}
                </p>
                {(item.detail ?? item.fact) ? (
                  <p className="mt-1 leading-6 text-zinc-500">
                    {item.detail ?? item.fact}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
        <h2 className="text-sm font-semibold">확인 범위와 한계</h2>
        <ul className="mt-3 space-y-2 text-xs leading-5 text-zinc-500">
          <li className="font-medium text-zinc-700">
            · Coverly는 보험을 팔지 않아요. 겹치거나 불필요한 보장을 먼저
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

function AmountReviewCard({ items }: { items: AmountReviewItem[] }) {
  return (
    <section className="rounded-2xl border border-zinc-200 p-6">
      <p className="text-xs font-semibold text-blue-700">금액 검토</p>
      <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em]">
        보험금 수준을 함께 살펴볼 항목
      </h2>

      {items.length ? (
        <ul className="mt-4 space-y-3">
          {items.map((item, index) => (
            <li
              key={`${item.coverage_name}-${index}`}
              className="rounded-xl bg-zinc-50 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-zinc-800">{item.title}</p>
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-500">
                  {formatConfidence(item.confidence)}
                </span>
              </div>

              <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
                <div className="flex gap-1.5">
                  <dt className="text-zinc-400">담보</dt>
                  <dd className="text-zinc-600">{item.coverage_name}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-zinc-400">현재 확인 금액</dt>
                  <dd className="text-zinc-600">
                    {item.current_amount === null
                      ? "없음"
                      : formatWon(item.current_amount)}
                  </dd>
                </div>
                {item.suggested_range ? (
                  <div className="flex gap-1.5">
                    <dt className="text-zinc-400">참고 범위</dt>
                    <dd className="text-zinc-600">{item.suggested_range}</dd>
                  </div>
                ) : null}
              </dl>

              <p className="mt-2 leading-6 text-zinc-600">{item.guidance}</p>
              <p className="mt-1 text-xs leading-5 text-zinc-400">
                {item.rationale}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm leading-6 text-zinc-500">
          현재 구조화된 정보만으로 별도 금액 검토 항목을 만들지 않았어요. 소득과
          생활비도 함께 살펴보면 좋아요.
        </p>
      )}
    </section>
  );
}

function ReviewCard({
  eyebrow,
  title,
  items,
  empty,
  tone = "default",
}: {
  eyebrow: string;
  title: string;
  items: Array<{ title: string; detail?: string }>;
  empty: string;
  tone?: "default" | "warning";
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
                <p className="mt-1 leading-6 text-zinc-500">{item.detail}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm leading-6 text-zinc-500">{empty}</p>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white bg-white px-4 py-4">
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-2 font-semibold text-zinc-900">{value}</dd>
    </div>
  );
}

function formatWon(amount: number) {
  return `${amount.toLocaleString("ko-KR")}원`;
}

function formatConfidence(confidence: "high" | "medium" | "low") {
  return {
    high: "높은 확신",
    medium: "보통 확신",
    low: "낮은 확신",
  }[confidence];
}
