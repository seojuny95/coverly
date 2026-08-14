import { useEffect, useRef } from "react";

// The progress bar deliberately trickles only to 90% so it never fakes a
// finish. This holds the finished state on screen briefly so the bar can
// actually reach 100% before the caller navigates away.
const COMPLETION_BEAT_MS = 400;

export function useCompletionDelay() {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const runAfterDelay = (action: () => void) => {
    if (!isMountedRef.current) return;
    // A second call before the first fires must not orphan the earlier timer
    // (it would keep running uncancellable after unmount).
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (isMountedRef.current) action();
    }, COMPLETION_BEAT_MS);
  };

  return { runAfterDelay };
}
