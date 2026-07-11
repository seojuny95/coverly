import type { PortfolioAnalysisResult } from "./portfolio-api";

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
  const amountReviewItems =
    result.counselor?.amount_review_items.map((item) => ({
      title: item.title,
      detail: [
        `담보 ${item.coverage_name}`,
        item.current_amount === null
          ? "현재 확인 금액 없음"
          : `현재 확인 금액 ${formatWon(item.current_amount)}`,
        `일반 가이드 · ${formatConfidence(item.confidence)}`,
        item.guidance,
        item.rationale,
        item.suggested_range ? `상담 참고 범위 ${item.suggested_range}` : null,
      ]
        .filter(Boolean)
        .join(" "),
    })) ?? [];
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
          상담 전 요약
        </p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em]">
          상담사가 먼저 살펴본 내용이에요
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
          title="상담에서 확인할 항목"
          items={gaps}
          empty="일반 확인 기준에서 빠진 항목을 찾지 못했어요."
          tone="warning"
        />
      </div>

      <ReviewCard
        eyebrow="금액 검토"
        title="보험금 수준을 함께 살펴볼 항목"
        items={amountReviewItems}
        empty="현재 구조화된 정보만으로 별도 금액 검토 항목을 만들지 않았어요. 상담에서 소득과 생활비를 함께 확인해보세요."
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <ReviewCard
          eyebrow="다음 질문"
          title="상담 전에 생각해볼 질문"
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
          empty="원본 약관과 최신 계약 상태를 상담사와 함께 확인해보세요."
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
          {limitations.map((item, index) => (
            <li key={`${item}-${index}`}>· {item}</li>
          ))}
          <li>· 자동차보험은 이번 분석에서 제외했어요.</li>
        </ul>
      </section>
    </div>
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
