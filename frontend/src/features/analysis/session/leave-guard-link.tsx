"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";

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
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent className="w-full max-w-sm rounded-2xl bg-white p-6 text-center">
          <AlertDialogHeader className="sm:place-items-center sm:text-center">
            <AlertDialogTitle className="text-lg font-semibold">
              지금 나가면 분석 내용이 지워져요
            </AlertDialogTitle>
            <AlertDialogDescription className="mt-2 text-sm leading-6 text-zinc-500">
              로그인 없이 보고 있어서, 화면을 벗어나면 올린 증권과 분석 결과가
              사라져요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-5 flex-row justify-center gap-2 border-t-0 bg-transparent p-0">
            <AlertDialogCancel>닫기</AlertDialogCancel>
            <AlertDialogAction
              className="bg-blue-600 hover:bg-blue-700"
              onClick={go}
            >
              나가기
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
