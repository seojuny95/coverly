import type { InsuranceCoverage } from "../upload/api";

const GENERATED_NOTICE =
  "증권에 설명이 없어 표준약관을 참고해 만든 안내예요. 정확한 내용은 가입한 상품의 약관에서 확인해 주세요.";

type InsuranceCoverageListProps = {
  coverages?: InsuranceCoverage[];
  status?: "완료" | "부분";
};

export function InsuranceCoverageList({
  coverages,
  status,
}: InsuranceCoverageListProps) {
  if (!coverages || coverages.length === 0) {
    // A partial analysis (e.g. an LLM error) must not look like a genuinely
    // empty insuranceDocument — tell the user it failed and what they can do.
    if (status === "부분") {
      return (
        <p className="text-sm leading-6 text-[#111827]/60">
          보장 내용을 다 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
        </p>
      );
    }
    return (
      <p className="text-sm leading-6 text-[#111827]/60">
        이 증권에서 보장 내용을 찾지 못했어요.
      </p>
    );
  }

  // Absent 유형 defaults to 담보 (existing non-auto documents never set it).
  const mainCoverages = coverages.filter(
    (coverage) => (coverage.유형 ?? "담보") === "담보",
  );
  const riderCoverages = coverages.filter(
    (coverage) => coverage.유형 === "부가",
  );

  return (
    <>
      {status === "부분" ? (
        <p className="mb-3 text-xs leading-5 text-[#111827]/50">
          일부 정보를 분석하지 못했어요.
        </p>
      ) : null}
      {mainCoverages.length > 0 ? (
        <ul className="divide-y divide-[#111827]/10">
          {mainCoverages.map((coverage, index) => (
            <li
              key={`${coverage.담보명}-${index}`}
              className="py-4 first:pt-0 last:pb-0"
            >
              <p className="text-sm font-semibold break-words text-[#111827]">
                {coverage.담보명}
              </p>
              {coverage.보장내용 ? (
                <p className="mt-1.5 text-sm leading-6 break-words whitespace-pre-line text-[#111827]/75">
                  {coverage.보장내용}
                </p>
              ) : coverage.해설 ? (
                <>
                  <p className="mt-1.5 text-sm leading-6 break-words whitespace-pre-line text-[#111827]/75">
                    {coverage.해설}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[#111827]/50">
                    {GENERATED_NOTICE}
                  </p>
                </>
              ) : null}
              <p className="mt-2 text-sm">
                {coverage.가입금액 === "확인필요" ? (
                  <span className="text-[#111827]/60">
                    보장 금액은 가입하신 상품의 약관에서 자세히 확인할 수 있어요
                  </span>
                ) : (
                  <span className="font-medium text-[#111827]">
                    {coverage.가입금액}
                  </span>
                )}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
      {riderCoverages.length > 0 ? (
        <div className={mainCoverages.length > 0 ? "mt-4" : undefined}>
          <p className="text-xs font-medium text-[#111827]/50">
            부가 특약·요율
          </p>
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1.5">
            {riderCoverages.map((coverage, index) => (
              <li
                key={`${coverage.담보명}-${index}`}
                className="text-sm break-words text-[#111827]/75"
              >
                {coverage.담보명}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}
