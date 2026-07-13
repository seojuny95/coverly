"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import type { InsuranceUploadResult } from "../insurance-upload/upload-insurance";
import { getPolicyIdentityKeys } from "./policy-identity";

export type AnalyzedInsurance = {
  id: string;
  fileName: string;
  fileFingerprint?: string;
  result: InsuranceUploadResult;
};

export type InsuranceAnalysis = {
  generatedAt: string;
  selectedName?: string;
  insuranceDocuments: AnalyzedInsurance[];
};

// Merge by document id first, then by policy identity as a defensive boundary.
export function mergeInsuranceAnalysis(
  current: InsuranceAnalysis,
  next: InsuranceAnalysis,
): InsuranceAnalysis {
  const byId = new Map<string, AnalyzedInsurance>();
  const existingIdentityKeys = new Set<string>();
  for (const document of current.insuranceDocuments)
    byId.set(document.id, document);

  for (const document of current.insuranceDocuments) {
    for (const key of getPolicyIdentityKeys(document)) {
      existingIdentityKeys.add(key);
    }
  }

  for (const document of next.insuranceDocuments) {
    const keys = getPolicyIdentityKeys(document);
    if (
      keys.some((key) => existingIdentityKeys.has(key)) &&
      !byId.has(document.id)
    ) {
      continue;
    }
    byId.set(document.id, document);
    for (const key of keys) {
      existingIdentityKeys.add(key);
    }
  }

  return {
    generatedAt: next.generatedAt,
    selectedName: next.selectedName ?? current.selectedName,
    insuranceDocuments: [...byId.values()],
  };
}

export function getInsuredPersonName(
  insuranceDocument: AnalyzedInsurance,
): string | null {
  return insuranceDocument.result.기본정보?.피보험자?.trim() || null;
}

type InsuranceDataValue = {
  analysis: InsuranceAnalysis | null;
  hasData: boolean;
  sessionExpired: boolean;
  setAnalysis: (next: InsuranceAnalysis) => void;
  mergeDocuments: (next: InsuranceAnalysis) => void;
  replaceDocumentSessionTokens: (
    replacements: readonly PolicySessionTokenReplacement[],
  ) => void;
  expireSession: () => void;
  clear: () => void;
};

export type PolicySessionTokenReplacement = {
  currentToken: string;
  nextToken: string;
};

const InsuranceDataContext = createContext<InsuranceDataValue | null>(null);

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

  const replaceDocumentSessionTokens = useCallback(
    (replacements: readonly PolicySessionTokenReplacement[]) => {
      if (!replacements.length) return;
      const nextTokensByCurrent = new Map(
        replacements.map(({ currentToken, nextToken }) => [
          currentToken,
          nextToken,
        ]),
      );
      setAnalysisState((current) => {
        if (!current) return current;
        return {
          ...current,
          insuranceDocuments: current.insuranceDocuments.map((document) => {
            const currentToken = document.result.문서세션ID;
            if (!currentToken) return document;
            const nextToken = nextTokensByCurrent.get(currentToken);
            if (!nextToken) return document;
            return {
              ...document,
              result: {
                ...document.result,
                문서세션ID: nextToken,
              },
            };
          }),
        };
      });
    },
    [],
  );

  const expireSession = useCallback(() => {
    setSessionExpired(true);
  }, []);

  // Discard the in-memory analysis. Called when the user leaves the analysis
  // screen so the "data disappears when you leave" warning stays true.
  const clear = useCallback(() => {
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
      replaceDocumentSessionTokens,
      expireSession,
      clear,
    }),
    [
      analysis,
      sessionExpired,
      setAnalysis,
      mergeDocuments,
      replaceDocumentSessionTokens,
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
