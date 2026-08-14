"use client";

import { useEffect } from "react";

// Warn on refresh/close while sensitive in-memory data exists.
// The dialog text is browser-controlled and cannot be customized.
export function useBeforeUnloadGuard(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [enabled]);
}
