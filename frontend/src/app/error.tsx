"use client";

import { useEffect } from "react";

import { ErrorScreen } from "@/shared/components/error-screen";

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
      name: error.name,
    });
  }, [error]);

  return <ErrorScreen digest={error.digest} onRetry={reset} />;
}
