import type { SpecialPolicyAnalysis } from "./api";

export function SpecialPolicySections({
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

            {analysis.classification_reasons?.length ? (
              <p className="border-t border-zinc-100 px-5 py-3 text-xs leading-5 text-zinc-500">
                {analysis.classification_reasons.join(" ")}
              </p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
