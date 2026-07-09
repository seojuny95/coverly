import type { PolicyCoverage } from "../policy-upload/upload-policy";

const GENERATED_NOTICE =
  "일반적인 설명이에요. 정확한 보장 내용은 가입한 상품의 약관에서 확인할 수 있어요.";

type PolicyCoverageListProps = {
  coverages?: PolicyCoverage[];
};

export function PolicyCoverageList({ coverages }: PolicyCoverageListProps) {
  if (!coverages || coverages.length === 0) {
    return (
      <p className="text-sm leading-6 text-[#111827]/60">
        이 증권에서 보장 내용을 찾지 못했어요.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-[#111827]/10">
      {coverages.map((coverage, index) => (
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
                가입금액은 확인이 필요해요
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
  );
}
