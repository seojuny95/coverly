"use client";

import { useEffect } from "react";

import { AppErrorFallback } from "@/components/app-error-fallback";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("app_render_error", {
      digest: error.digest,
      message: error.message,
      name: error.name,
    });
  }, [error]);

  return <AppErrorFallback digest={error.digest} onRetry={reset} />;
}
