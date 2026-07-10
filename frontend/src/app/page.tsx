import Link from "next/link";

import {
  CoverlyLogo,
  PixelEyebrow,
  primaryButtonClassName,
} from "@/components/coverly-brand";

const insuranceSources = [
  { company: "보험사 A", type: "생명보험" },
  { company: "보험사 B", type: "손해보험" },
  { company: "보험사 C", type: "건강보험" },
];

const resultRows = ["가입 내역 연결", "보장별로 정리", "확인 근거 포함"];

function InsuranceCard({
  company,
  type,
  index,
  compact = false,
}: {
  company: string;
  type: string;
  index: number;
  compact?: boolean;
}) {
  return (
    <div
      className={`evidence-source evidence-source-${index + 1} relative overflow-hidden rounded-xl border border-zinc-200 bg-white text-left shadow-[0_8px_25px_rgba(24,24,27,0.04)] ${
        compact ? "px-2.5 py-2.5" : "px-3.5 py-3"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="grid size-5 shrink-0 place-items-center rounded-md border border-zinc-200 bg-zinc-50">
          <span className="size-1.5 bg-zinc-400" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[10px] font-semibold text-zinc-800 sm:text-[11px]">
            {company}
          </span>
          <span className="mt-0.5 block truncate text-[8px] text-zinc-400 sm:text-[9px]">
            {type}
          </span>
        </span>
      </div>
      <div className="mt-2.5 space-y-1.5">
        <span className="block h-px w-full bg-zinc-200" />
        <span className="block h-px w-2/3 bg-zinc-200" />
      </div>
    </div>
  );
}

function CoverageMap({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`evidence-result rounded-2xl border border-zinc-200 bg-white text-left shadow-[10px_10px_0_#e8edff] ${
        compact ? "mx-auto w-[250px] p-4" : "w-full p-5"
      }`}
    >
      <div className="flex items-start justify-between">
        <span>
          <span className="block font-mono text-[8px] tracking-[0.08em] text-zinc-400">
            보장 분석
          </span>
          <strong className="mt-1.5 block text-sm font-semibold tracking-[-0.04em] text-zinc-950">
            나의 보장 지도
          </strong>
        </span>
        <span className="evidence-complete grid size-6 place-items-center rounded-lg bg-blue-600 text-white">
          <svg
            aria-hidden="true"
            className="size-3.5"
            viewBox="0 0 14 14"
            fill="none"
          >
            <path
              d="m3 7 2.5 2.5L11 4.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="square"
            />
          </svg>
        </span>
      </div>

      <div className="mt-4 space-y-1.5">
        {resultRows.map((row, index) => (
          <div
            key={row}
            className={`evidence-result-row evidence-result-row-${index + 1} flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[9px] text-zinc-600 sm:text-[10px]`}
          >
            <span className="size-1.5 shrink-0 bg-blue-600" />
            {row}
          </div>
        ))}
      </div>
    </div>
  );
}

function DesktopRoutes() {
  const routes = [
    "M0 44C92 44 118 92 205 94C292 96 324 58 420 58",
    "M0 110C112 110 132 110 205 110C286 110 312 110 420 110",
    "M0 176C92 176 118 128 205 126C292 124 324 162 420 162",
  ];

  return (
    <svg
      aria-hidden="true"
      className="h-[220px] w-full overflow-visible"
      viewBox="0 0 420 220"
      fill="none"
      preserveAspectRatio="none"
    >
      <circle className="evidence-glow" cx="205" cy="110" r="38" />
      {routes.map((route, index) => (
        <g key={route}>
          <path className="evidence-route" d={route} pathLength="1" />
          <path
            className={`evidence-signal evidence-signal-${index + 1}`}
            d={route}
            pathLength="1"
          />
        </g>
      ))}
      <path
        className="evidence-stitch"
        d="M205 82v56M197 94h16M197 110h16M197 126h16"
      />
    </svg>
  );
}

function MobileRoutes() {
  const routes = [
    "M48 0C48 34 112 26 160 60V92",
    "M160 0V92",
    "M272 0C272 34 208 26 160 60V92",
  ];

  return (
    <svg
      aria-hidden="true"
      className="h-24 w-full overflow-visible"
      viewBox="0 0 320 96"
      fill="none"
      preserveAspectRatio="none"
    >
      <circle className="evidence-glow" cx="160" cy="58" r="28" />
      {routes.map((route, index) => (
        <g key={route}>
          <path className="evidence-route" d={route} pathLength="1" />
          <path
            className={`evidence-signal evidence-signal-${index + 1}`}
            d={route}
            pathLength="1"
          />
        </g>
      ))}
    </svg>
  );
}

function EvidenceWeave() {
  return (
    <figure
      className="evidence-weave relative mx-auto mt-12 w-full max-w-4xl sm:mt-14"
      role="img"
      aria-label="서로 다른 보험사의 가입 내역이 연결되어 하나의 보장 지도로 정리되는 과정"
    >
      <div className="evidence-dot-grid absolute inset-0" aria-hidden="true" />

      <div
        className="relative hidden grid-cols-[150px_minmax(180px,1fr)_210px] items-center gap-4 sm:grid"
        aria-hidden="true"
      >
        <div className="space-y-2.5">
          {insuranceSources.map((source, index) => (
            <InsuranceCard key={source.company} {...source} index={index} />
          ))}
        </div>
        <DesktopRoutes />
        <CoverageMap />
      </div>

      <div className="relative sm:hidden" aria-hidden="true">
        <div className="grid grid-cols-3 gap-2">
          {insuranceSources.map((source, index) => (
            <InsuranceCard
              key={source.company}
              {...source}
              index={index}
              compact
            />
          ))}
        </div>
        <MobileRoutes />
        <CoverageMap compact />
      </div>

      <figcaption className="relative mt-5 flex items-center justify-center gap-3 font-mono text-[9px] tracking-[0.08em] text-zinc-400 sm:mt-6 sm:text-[10px]">
        <span>FIND</span>
        <span className="size-1 bg-zinc-300" />
        <span>CONNECT</span>
        <span className="size-1 bg-blue-600" />
        <span>UNDERSTAND</span>
      </figcaption>
    </figure>
  );
}

export default function Home() {
  return (
    <main className="overflow-hidden bg-white text-zinc-950">
      <section className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-6 pt-24 pb-10 text-center sm:pt-28 sm:pb-14 lg:px-8">
        <CoverlyLogo className="absolute top-6 left-6 lg:left-8" />

        <div className="mb-6">
          <PixelEyebrow>보험을 찾고 연결하는 AI</PixelEyebrow>
        </div>

        <h1 className="max-w-5xl text-[2.25rem] leading-[1.04] font-semibold tracking-[-0.075em] [word-break:keep-all] text-zinc-950 sm:text-[clamp(3.5rem,7.2vw,6.7rem)] sm:leading-[1.01]">
          <span className="block whitespace-nowrap">보험은 흩어져 있어도,</span>
          <span className="block whitespace-nowrap text-zinc-400">
            이해는 한 번에.
          </span>
        </h1>

        <p className="mt-7 max-w-2xl text-base leading-7 [word-break:keep-all] text-zinc-600 sm:text-lg sm:leading-8">
          여러 보험사에 나뉜 가입 내역을 찾아 연결하고,
          <br className="hidden sm:block" /> 보장 범위와 중복 여부를 확인한
          근거와 함께 정리해요.
        </p>

        <Link href="/upload" className={`mt-8 ${primaryButtonClassName}`}>
          내 보험 분석하기
        </Link>

        <EvidenceWeave />
      </section>
    </main>
  );
}
