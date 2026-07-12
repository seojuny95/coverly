import Link from "next/link";

export const primaryButtonClassName =
  "inline-flex min-h-11 items-center justify-center rounded-lg bg-zinc-950 px-5 py-3 text-sm font-medium text-white transition-all hover:-translate-y-0.5 hover:bg-zinc-800 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-zinc-100 disabled:text-zinc-400 disabled:hover:translate-y-0 disabled:hover:shadow-none";

export const secondaryButtonClassName =
  "inline-flex min-h-11 items-center justify-center rounded-lg border border-zinc-200 bg-white px-5 py-3 text-sm font-medium text-zinc-800 transition-colors hover:border-zinc-300 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2";

export const ghostButtonClassName =
  "inline-flex min-h-10 items-center justify-center rounded-lg px-3 py-2 text-sm font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600";

export const coverlyLogoLinkClassName =
  "group flex items-center gap-1.5 outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-4";

// Visual mark only, no navigation. Lets call sites that need custom link
// behavior (e.g. a leave-confirmation guard) compose their own wrapper
// while keeping the markup identical to CoverlyLogo.
export function CoverlyMark() {
  return (
    <>
      <span className="text-[19px] font-semibold tracking-[-0.065em] text-zinc-950">
        coverly
      </span>
      <span
        className="size-1.5 translate-y-0.5 bg-blue-600 shadow-[3px_3px_0_#dbeafe]"
        aria-hidden="true"
      />
    </>
  );
}

export function CoverlyLogo({ className = "" }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`${coverlyLogoLinkClassName} ${className}`}
      aria-label="Coverly 홈"
    >
      <CoverlyMark />
    </Link>
  );
}

export function PixelEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-2 font-mono text-[10px] font-medium tracking-[0.08em] text-zinc-500 sm:text-[11px]">
      <span className="size-1.5 bg-blue-600" aria-hidden="true" />
      {children}
    </p>
  );
}
