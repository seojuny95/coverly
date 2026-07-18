import Link from "next/link";

export const logoLinkClassName =
  "group flex items-center gap-1.5 outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-4";

// Visual mark only, no navigation. Lets call sites that need custom link
// behavior (e.g. a leave-confirmation guard) compose their own wrapper.
export function CoverlyMark() {
  return (
    <>
      <span className="text-[19px] font-semibold tracking-[-0.065em] text-zinc-950">
        coverly<span className="text-blue-600"> AI</span>
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
      className={`${logoLinkClassName} ${className}`}
      aria-label="Coverly AI 홈"
    >
      <CoverlyMark />
    </Link>
  );
}
