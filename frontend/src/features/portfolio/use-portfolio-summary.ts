"use client";

import { useCallback, useEffect, useState } from "react";
import type { AnalyzedInsurance } from "../insurance-analysis/insurance-analysis-store";
import {
  type PortfolioSummary,
  requestPortfolioSummary,
} from "./portfolio-api";

type SummaryState =
  | { status: "loading" }
  | { status: "success"; summary: PortfolioSummary }
  | { status: "error" };

export function usePortfolioSummary(documents: AnalyzedInsurance[]) {
  const [state, setState] = useState<SummaryState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void requestPortfolioSummary(documents, controller.signal)
      .then((summary) => setState({ status: "success", summary }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError")
          setState({ status: "error" });
      });
    return () => controller.abort();
  }, [attempt, documents]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);
  return { state, retry };
}
