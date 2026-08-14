import type { QueryClient } from "@tanstack/react-query";

export const ANALYSIS_QUERY_KEY = ["analysis"] as const;

export function removeAnalysisCache(queryClient: QueryClient): void {
  queryClient.removeQueries({ queryKey: ANALYSIS_QUERY_KEY });

  const mutationCache = queryClient.getMutationCache();
  for (const mutation of mutationCache.findAll({
    mutationKey: ANALYSIS_QUERY_KEY,
  })) {
    mutationCache.remove(mutation);
  }
}
