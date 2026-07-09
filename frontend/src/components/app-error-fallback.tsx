"use client";

type AppErrorFallbackProps = {
  digest?: string;
  onRetry?: () => void;
};

export function AppErrorFallback({ digest, onRetry }: AppErrorFallbackProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f5f7] px-5 py-12 text-zinc-950">
      <section className="w-full max-w-md rounded-[8px] border border-zinc-200 bg-white px-5 py-6 shadow-[0_16px_60px_rgba(0,0,0,0.06)] sm:px-7 sm:py-7">
        <p className="text-sm font-semibold text-zinc-950">Coverly</p>
        <h1 className="mt-5 text-2xl leading-8 font-semibold tracking-normal">
          화면을 불러오지 못했습니다.
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          일시적인 오류일 수 있습니다. 다시 시도해도 문제가 계속되면 잠시 후
          접속해주세요.
        </p>
        {digest ? (
          <p className="mt-4 rounded-[8px] bg-zinc-50 px-3 py-2 font-mono text-xs text-zinc-500">
            오류 ID: {digest}
          </p>
        ) : null}
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-6 rounded-[8px] bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2 focus:outline-none"
          >
            다시 시도
          </button>
        ) : null}
      </section>
    </main>
  );
}
