import { Skeleton } from "@/shared/components/ui/skeleton";

export function AnalysisLoading() {
  return (
    <section
      aria-live="polite"
      aria-busy="true"
      className="rounded-2xl border border-zinc-200 p-8"
    >
      <Skeleton className="h-2 w-20 bg-blue-600" />
      <h2 className="mt-5 text-xl font-semibold">
        전체 보험의 핵심 보장을 확인하고 있어요
      </h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">
        사망·3대 진단비·실손의료비와 보험 종류별 담보를 정리하고 있어요.
      </p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((item) => (
          <Skeleton key={item} className="h-40 rounded-xl" />
        ))}
      </div>
    </section>
  );
}
