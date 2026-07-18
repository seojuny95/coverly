import type { ReactNode } from "react";

export function PolicyDocumentGuide() {
  return (
    <details
      data-testid="policy-document-guide"
      className="group mt-5 overflow-hidden rounded-xl border border-zinc-200 bg-zinc-50 open:bg-white"
    >
      <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2.5 px-4 text-left text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-none focus-visible:ring-inset [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="size-3 rounded-[3px] border border-blue-300 bg-blue-50"
        />
        <span className="flex-1">보험증권을 어디서 받는지 모르겠어요</span>
        <svg
          aria-hidden="true"
          className="size-4 text-zinc-500 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none"
          viewBox="0 0 16 16"
          fill="none"
        >
          <path
            d="m4 6 4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="square"
          />
        </svg>
      </summary>

      <div className="border-t border-zinc-200 px-4 pt-5 pb-4 sm:px-5 sm:pt-6 sm:pb-5">
        <h2 className="text-base font-semibold tracking-[-0.025em] text-zinc-950 sm:text-lg">
          보험증권을 이렇게 받을 수 있어요
        </h2>

        <div className="mt-4 rounded-xl bg-zinc-50 p-4">
          <GuideStepNumber>1</GuideStepNumber>
          <div className="mt-3">
            <h3 className="text-sm font-semibold text-zinc-800">
              가입한 보험사를 알고 있다면
            </h3>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              보험사 앱·홈페이지 → 계약 관리 또는 증명서 발급 → 보험증권 → PDF
              저장
            </p>
            <p className="mt-1 text-xs leading-5 text-zinc-400">
              보험사마다 메뉴 이름은 조금 다를 수 있어요.
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 px-1 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <GuideStepNumber muted>2</GuideStepNumber>
            <div>
              <h3 className="text-sm font-semibold text-zinc-800">
                가입한 보험사가 기억나지 않는다면
              </h3>
              <p className="mt-1 text-sm leading-6 text-zinc-600">
                내보험찾아줌에서 보험사를 먼저 확인할 수 있어요.
              </p>
            </div>
          </div>
          <a
            href="https://cont.insure.or.kr/cont_web/intro.do"
            target="_blank"
            rel="noreferrer"
            aria-label="가입한 보험사 확인 (새 창에서 열기)"
            className="inline-flex min-h-10 shrink-0 items-center justify-center self-start rounded-lg bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 focus-visible:outline-none sm:self-auto"
          >
            가입한 보험사 확인
            <span className="ml-1" aria-hidden="true">
              ↗
            </span>
          </a>
        </div>

        <p className="mt-5 border-t border-zinc-100 pt-4 text-xs leading-5 text-zinc-400">
          약관이나 납입증명서가 아닌 ‘보험증권’ PDF를 올려주세요.
        </p>
      </div>
    </details>
  );
}

function GuideStepNumber({
  children,
  muted = false,
}: {
  children: ReactNode;
  muted?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={`grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold ${
        muted ? "bg-blue-100 text-blue-700" : "bg-blue-600 text-white"
      }`}
    >
      {children}
    </span>
  );
}
