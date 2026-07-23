"use client";

import { useEffect } from "react";

import { ErrorScreen } from "@/shared/components/error-screen";

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
      name: error.name,
    });
  }, [error]);

  return (
    <html lang="ko">
      <body>
        <ErrorScreen digest={error.digest} onRetry={reset} showBrand />
      </body>
    </html>
  );
}
