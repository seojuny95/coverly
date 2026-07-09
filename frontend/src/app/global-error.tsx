"use client";

import { useEffect } from "react";

import { AppErrorFallback } from "@/components/app-error-fallback";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("global_render_error", {
      digest: error.digest,
      message: error.message,
      name: error.name,
    });
  }, [error]);

  return (
    <html lang="ko">
      <body>
        <AppErrorFallback digest={error.digest} onRetry={reset} />
      </body>
    </html>
  );
}
