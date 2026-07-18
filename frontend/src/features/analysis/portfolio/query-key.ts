import type { AnalyzedInsurance } from "../store";

// Content-derived cache key for a set of documents: changes whenever a
// document is added/removed or its parsed content changes, so react-query
// keys and dependency arrays invalidate correctly. Must be derived from
// whatever set of documents actually gets sent to the backend by the caller.
export function portfolioKey(documents: AnalyzedInsurance[]): string {
  return documents
    .map((document) => `${document.id}:${document.result.문자수}`)
    .join("|");
}
