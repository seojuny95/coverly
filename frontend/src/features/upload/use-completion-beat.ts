"use client";

import { useEffect, useRef, useState } from "react";

// The progress bar deliberately trickles only to 90% so it never fakes a
// finish. This holds the finished state on screen briefly so the bar can
// actually reach 100% before the caller navigates away.
const COMPLETION_BEAT_MS = 400;

export function useCompletionBeat() {
  const [isCompleting, setIsCompleting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const runAfterBeat = (action: () => void) => {
    // A second call before the first fires must not orphan the earlier timer
    // (it would keep running uncancellable after unmount).
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsCompleting(true);
    timerRef.current = setTimeout(action, COMPLETION_BEAT_MS);
  };

  return { isCompleting, runAfterBeat };
}
