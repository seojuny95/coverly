import type { AnalyzedInsurance } from "../session/store";
import type { DeathBenefitGuideInput } from "./types";
import { ANALYSIS_QUERY_KEY } from "../query-cache";

export const PORTFOLIO_SUMMARY_QUERY_KEY = [
  ...ANALYSIS_QUERY_KEY,
  "portfolio-summary",
] as const;

// Content-derived cache key for a set of documents: changes whenever a
// document is added/removed or its parsed content changes, so react-query
// keys and dependency arrays invalidate correctly. Must be derived from
// whatever set of documents actually gets sent to the backend by the caller.
export function portfolioKey(documents: AnalyzedInsurance[]): string {
  return documents
    .map((document) => {
      const source = document.fileFingerprint ?? "no-file-fingerprint";
      const parsedResult = contentFingerprint(document.result);
      return `${document.id}:${source}:${parsedResult}`;
    })
    .sort()
    .join("|");
}

function contentFingerprint(value: unknown): string {
  const serialized = JSON.stringify(value);
  let first = 0x811c9dc5;
  let second = 0x9e3779b9;

  for (let index = 0; index < serialized.length; index += 1) {
    const code = serialized.charCodeAt(index);
    first = Math.imul(first ^ code, 0x01000193);
    second = Math.imul(second ^ code, 0x85ebca6b);
  }

  return [
    serialized.length.toString(36),
    (first >>> 0).toString(36),
    (second >>> 0).toString(36),
  ].join("-");
}

export function portfolioSummaryQueryKey(
  documents: AnalyzedInsurance[],
  deathBenefitContext: DeathBenefitGuideInput,
) {
  return [
    ...PORTFOLIO_SUMMARY_QUERY_KEY,
    portfolioKey(documents),
    deathBenefitContext.has_dependent_family,
    deathBenefitContext.has_minor_children,
    deathBenefitContext.has_major_debt,
  ] as const;
}
