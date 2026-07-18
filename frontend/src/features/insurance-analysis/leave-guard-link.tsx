"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState, type ReactNode } from "react";
import { useDialogA11y } from "./use-dialog-a11y";

// In-app navigation guard: when `enabled`, intercepts the click and shows a
// custom confirm modal before leaving (in-memory analysis data would be lost).
export function LeaveGuardLink({
  href,
  enabled,
  children,
  className,
  ariaLabel,
}: {
  href: string;
  enabled: boolean;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const closeDialog = useCallback(() => setOpen(false), []);
  const dialogRef = useDialogA11y<HTMLDivElement>({
    open,
    onClose: closeDialog,
  });

  const go = () => router.push(href);

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
          ref={dialogRef}
          role="dialog"
          aria-modal
          aria-labelledby="leave-guard-title"
          tabIndex={-1}
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
                onClick={closeDialog}
              >
                닫기
              </button>
              <button
                type="button"
                className="rounded-xl bg-blue-600 px-4 py-2 text-sm text-white"
                onClick={go}
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
