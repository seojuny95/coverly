"use client";

import { useState } from "react";

import { PolicyUploadForm } from "./form/upload-form";
import { SamplePortfolioOption } from "./sample/option";
import { useSamplePortfolio } from "./sample/use-sample-portfolio";

export function UploadOptions() {
  const [uploadInteractionLocked, setUploadInteractionLocked] = useState(false);
  const sample = useSamplePortfolio(uploadInteractionLocked);

  return (
    <div className="w-full max-w-2xl">
      <PolicyUploadForm
        disabled={sample.isLoading}
        onInteractionLockedChange={setUploadInteractionLocked}
      />

      <div className="my-6 flex items-center gap-4" aria-hidden="true">
        <span className="h-px flex-1 bg-zinc-200" />
        <span className="text-xs text-zinc-400">또는</span>
        <span className="h-px flex-1 bg-zinc-200" />
      </div>

      <SamplePortfolioOption
        disabled={uploadInteractionLocked}
        error={sample.error}
        loadingStep={sample.loadingStep}
        onOpen={sample.open}
      />
    </div>
  );
}
