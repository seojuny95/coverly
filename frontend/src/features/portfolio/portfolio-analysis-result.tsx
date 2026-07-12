import type { PortfolioAnalysisResult } from "./portfolio-api";

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

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-blue-100 bg-blue-50/50 p-6 sm:p-8">
        <p className="text-xs font-semibold tracking-[0.12em] text-blue-700 uppercase">
          내 보험 상담
        </p>
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-2xl font-semibold tracking-[-0.04em]">
            Coverly가 {insuredName ? `${insuredName}님` : "당신"} 편에서
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
          eyebrow="현재 강점"
          title="잘 가입돼 있는 부분"
          items={strengths}
          empty="현재 데이터에서 뚜렷한 강점을 확인하지 못했어요."
        />
        <ReviewCard
          eyebrow="현재 부족한 점"
          title="과하거나 부족한 부분"
          items={gaps}
          empty="지금 데이터에서 과하거나 부족한 점을 찾지 못했어요."
          tone="warning"
        />
      </div>

      <section className="rounded-2xl border border-zinc-200 p-6">
        <p className="text-xs font-semibold text-blue-700">총평</p>
        <p className="mt-3 text-sm leading-7 text-zinc-700">
          {result.counselor?.overview ??
            `${result.life_stage} 기준으로 보험 ${result.policy_count}건에서 확인 가능한 보장을 정리했어요.`}
        </p>
      </section>

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
