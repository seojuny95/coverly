"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { createSamplePortfolioSession } from "@/features/analysis/session/api";
import { useInsuranceData } from "@/features/analysis/session/store";
import {
  isAbortError,
  reportClientOperationFailure,
  userMessageForError,
} from "@/shared/api/errors";
import { waitForBackendReady } from "@/shared/api/readiness";
import { sampleSessionToAnalysis } from "./to-analysis";

export type SampleLoadingStep = "idle" | "checking" | "creating" | "navigating";

export function useSamplePortfolio(interactionLocked: boolean) {
  const router = useRouter();
  const { setAnalysis } = useInsuranceData();
  const controllerRef = useRef<AbortController | null>(null);
  const [loadingStep, setLoadingStep] = useState<SampleLoadingStep>("idle");
  const [error, setError] = useState<string | null>(null);
  const isLoading = loadingStep !== "idle";

  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const open = async () => {
    if (interactionLocked || isLoading) return;

    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    let didNavigate = false;

    setLoadingStep("checking");
    setError(null);
    try {
      await waitForBackendReady({ signal: controller.signal });
      setLoadingStep("creating");

      const sample = await createSamplePortfolioSession(controller.signal);
      if (controller.signal.aborted) return;

      setAnalysis(sampleSessionToAnalysis(sample));
      setLoadingStep("navigating");
      didNavigate = true;
      router.push("/analysis");
    } catch (requestError) {
      if (controller.signal.aborted || isAbortError(requestError)) return;
      reportClientOperationFailure("sample_portfolio_create", requestError);
      setError(
        userMessageForError(
          requestError,
          "샘플 분석을 준비하지 못했어요. 잠시 후 다시 시도해주세요.",
        ),
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        if (!didNavigate) setLoadingStep("idle");
      }
    }
  };

  return { error, isLoading, loadingStep, open };
}
