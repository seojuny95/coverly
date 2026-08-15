"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { InsuranceAnalysis } from "../types";
import { reportClientOperationFailure } from "@/shared/api/errors";
import { deletePortfolioSession, type PortfolioSessionResult } from "./api";
import { mergeInsuranceAnalysis } from "./merge-analysis";

export type { AnalyzedInsurance, InsuranceAnalysis } from "../types";

type InsuranceDataValue = {
  analysis: InsuranceAnalysis | null;
  hasData: boolean;
  sessionExpired: boolean;
  setAnalysis: (next: InsuranceAnalysis) => void;
  mergeDocuments: (next: InsuranceAnalysis) => void;
  replacePortfolioSession: (session: PortfolioSessionResult) => void;
  expireSession: () => void;
  clear: () => void;
};

const InsuranceDataContext = createContext<InsuranceDataValue | null>(null);

function disposePortfolioSession(portfolioSessionToken?: string) {
  if (!portfolioSessionToken) return;

  void deletePortfolioSession(portfolioSessionToken).catch((error: unknown) => {
    reportClientOperationFailure("portfolio_session_delete", error);
  });
}

export function InsuranceDataProvider({
  children,
  initialAnalysis = null,
}: {
  children: React.ReactNode;
  // Test-only seed for the in-memory analysis; harmless in production (defaults null).
  initialAnalysis?: InsuranceAnalysis | null;
}) {
  const [analysis, setAnalysisState] = useState<InsuranceAnalysis | null>(
    initialAnalysis,
  );
  const [sessionExpired, setSessionExpired] = useState(false);
  const portfolioSessionTokenRef = useRef(
    initialAnalysis?.portfolioSessionToken,
  );

  useEffect(() => {
    portfolioSessionTokenRef.current = analysis?.portfolioSessionToken;
  }, [analysis?.portfolioSessionToken]);

  useEffect(
    () => () => {
      const portfolioSessionToken = portfolioSessionTokenRef.current;
      portfolioSessionTokenRef.current = undefined;
      disposePortfolioSession(portfolioSessionToken);
    },
    [],
  );

  const setAnalysis = useCallback((next: InsuranceAnalysis) => {
    setSessionExpired(false);
    setAnalysisState(next);
  }, []);

  const mergeDocuments = useCallback((next: InsuranceAnalysis) => {
    setSessionExpired(false);
    setAnalysisState((current) =>
      current ? mergeInsuranceAnalysis(current, next) : next,
    );
  }, []);

  const replacePortfolioSession = useCallback(
    (session: PortfolioSessionResult) => {
      setAnalysisState((current) =>
        current
          ? {
              ...current,
              portfolioSessionToken: session.portfolioSessionToken,
              portfolioSessionExpiresAt: session.expiresAt,
              counselTurnsRemaining: session.counselTurnsRemaining,
              portfolioKind: session.portfolioKind,
            }
          : current,
      );
    },
    [],
  );

  const expireSession = useCallback(() => {
    setSessionExpired(true);
  }, []);

  // Discard the in-memory analysis after the user leaves all analysis routes.
  const clear = useCallback(() => {
    const portfolioSessionToken = portfolioSessionTokenRef.current;
    portfolioSessionTokenRef.current = undefined;
    disposePortfolioSession(portfolioSessionToken);
    setSessionExpired(false);
    setAnalysisState(null);
  }, []);

  const value = useMemo<InsuranceDataValue>(
    () => ({
      analysis,
      hasData: (analysis?.insuranceDocuments.length ?? 0) > 0,
      sessionExpired,
      setAnalysis,
      mergeDocuments,
      replacePortfolioSession,
      expireSession,
      clear,
    }),
    [
      analysis,
      sessionExpired,
      setAnalysis,
      mergeDocuments,
      replacePortfolioSession,
      expireSession,
      clear,
    ],
  );

  return (
    <InsuranceDataContext.Provider value={value}>
      {children}
    </InsuranceDataContext.Provider>
  );
}

export function useInsuranceData(): InsuranceDataValue {
  const value = useContext(InsuranceDataContext);
  if (!value)
    throw new Error(
      "useInsuranceData must be used within InsuranceDataProvider",
    );
  return value;
}
