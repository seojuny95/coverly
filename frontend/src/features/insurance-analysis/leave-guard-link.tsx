"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

// In-app navigation guard: when `enabled`, intercepts the click and shows a
// custom confirm modal before leaving (in-memory analysis data would be lost).
export function LeaveGuardLink({
  href,
  enabled,
  onLeave,
  children,
  className,
  ariaLabel,
}: {
  href: string;
  enabled: boolean;
  // Called right before navigating away when the user confirms leaving
  // (e.g. to discard in-memory data so the warning copy stays accurate).
  onLeave?: () => void;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const go = () => router.push(href);

  const confirmLeave = () => {
    onLeave?.();
    go();
  };

  return (
    <>
      <a
        href={href}
        className={className}
        aria-label={ariaLabel}
        onClick={(event) => {
          event.preventDefault();
          if (enabled) setOpen(true);
          else go();
        }}
      >
        {children}
      </a>
      {open ? (
        <div
          role="dialog"
          aria-modal
          aria-labelledby="leave-guard-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-5"
        >
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 text-center">
            <h2 id="leave-guard-title" className="text-lg font-semibold">
              지금 나가면 분석 내용이 지워져요
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">
              로그인 없이 보고 있어서, 화면을 벗어나면 올린 증권과 분석 결과가
              사라져요.
            </p>
            <div className="mt-5 flex justify-center gap-2">
              <button
                type="button"
                className="rounded-xl border px-4 py-2 text-sm"
                onClick={() => setOpen(false)}
              >
                닫기
              </button>
              <button
                type="button"
                className="rounded-xl bg-blue-600 px-4 py-2 text-sm text-white"
                onClick={confirmLeave}
              >
                나가기
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
