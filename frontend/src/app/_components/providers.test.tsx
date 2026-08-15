import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Providers } from "./providers";
import { useInsuranceData } from "@/features/analysis/session/store";
import { POLICY_RESULT_DEFAULTS } from "@/test/api-fixtures";
import { ANALYSIS_QUERY_KEY } from "@/features/analysis/query-cache";
import { isAnalysisPath } from "@/features/analysis/routes";

const navigation = vi.hoisted(() => ({ pathname: "/upload" }));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
}));

function Probe() {
  const { data } = useQuery({
    queryKey: ["probe"],
    queryFn: () => Promise.resolve("ok"),
  });
  return <span>{data ?? "loading"}</span>;
}

function InsuranceDataProbe() {
  const { hasData, setAnalysis } = useInsuranceData();
  return (
    <>
      <button
        type="button"
        onClick={() =>
          setAnalysis({
            generatedAt: "2026-07-12T00:00:00.000Z",
            portfolioKind: "uploaded" as const,
            portfolioSessionToken: "test-portfolio-token",
            portfolioSessionExpiresAt: "2030-01-01T00:00:00.000Z",
            counselTurnsRemaining: 10,
            insuranceDocuments: [
              {
                id: "policy-1",
                fileName: "policy.pdf",
                result: {
                  ...POLICY_RESULT_DEFAULTS,
                  status: "accepted",
                  문자수: 1,
                },
              },
            ],
          })
        }
      >
        seed
      </button>
      <span>{hasData ? "has-data" : "empty"}</span>
    </>
  );
}

function AnalysisQueryProbe() {
  const queryClient = useQueryClient();
  const [cacheState, setCacheState] = useState("not-inspected");
  const { data } = useQuery({
    queryKey: [...ANALYSIS_QUERY_KEY, "test-sensitive-result"],
    queryFn: () => Promise.resolve("cached-analysis"),
    enabled: isAnalysisPath(navigation.pathname),
  });

  return (
    <>
      <span>{data ?? "no-analysis-cache"}</span>
      <button
        type="button"
        onClick={() =>
          setCacheState(
            queryClient.getQueriesData({ queryKey: ANALYSIS_QUERY_KEY })
              .length === 0
              ? "cache-empty"
              : "cache-retained",
          )
        }
      >
        inspect cache
      </button>
      <span>{cacheState}</span>
    </>
  );
}

describe("Providers", () => {
  beforeEach(() => {
    navigation.pathname = "/upload";
  });

  it("supplies a QueryClient to children", async () => {
    render(
      <Providers>
        <Probe />
      </Providers>,
    );
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("clears analysis state and cache after leaving the analysis route", async () => {
    navigation.pathname = "/analysis";
    const { rerender } = render(
      <Providers>
        <InsuranceDataProbe />
        <AnalysisQueryProbe />
      </Providers>,
    );

    fireEvent.click(screen.getByRole("button", { name: "seed" }));
    expect(screen.getByText("has-data")).toBeInTheDocument();
    expect(await screen.findByText("cached-analysis")).toBeInTheDocument();

    navigation.pathname = "/upload";
    rerender(
      <Providers>
        <InsuranceDataProbe />
        <AnalysisQueryProbe />
      </Providers>,
    );

    await waitFor(() => expect(screen.getByText("empty")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "inspect cache" }));
    expect(screen.getByText("cache-empty")).toBeInTheDocument();
  });

  it("keeps in-memory analysis while navigating between analysis routes", () => {
    navigation.pathname = "/analysis";
    const { rerender } = render(
      <Providers>
        <InsuranceDataProbe />
      </Providers>,
    );

    fireEvent.click(screen.getByRole("button", { name: "seed" }));
    navigation.pathname = "/analysis/coverage";
    rerender(
      <Providers>
        <InsuranceDataProbe />
      </Providers>,
    );

    expect(screen.getByText("has-data")).toBeInTheDocument();
  });
});
