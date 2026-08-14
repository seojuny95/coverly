import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { ANALYSIS_QUERY_KEY, removeAnalysisCache } from "./query-cache";

describe("removeAnalysisCache", () => {
  it("removes only analysis queries and mutations", () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData([...ANALYSIS_QUERY_KEY, "summary"], "sensitive");
    queryClient.setQueryData(["upload", "status"], "safe");

    const mutationCache = queryClient.getMutationCache();
    mutationCache.build(queryClient, {
      mutationKey: [...ANALYSIS_QUERY_KEY, "overview"],
      mutationFn: async () => "sensitive",
    });
    mutationCache.build(queryClient, {
      mutationKey: ["upload", "submit"],
      mutationFn: async () => "safe",
    });

    removeAnalysisCache(queryClient);

    expect(
      queryClient.getQueriesData({ queryKey: ANALYSIS_QUERY_KEY }),
    ).toEqual([]);
    expect(queryClient.getQueryData(["upload", "status"])).toBe("safe");
    expect(mutationCache.findAll({ mutationKey: ANALYSIS_QUERY_KEY })).toEqual(
      [],
    );
    expect(mutationCache.findAll({ mutationKey: ["upload"] })).toHaveLength(1);
  });
});
