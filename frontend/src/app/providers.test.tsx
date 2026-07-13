import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { Providers } from "./providers";
import { useInsuranceData } from "../features/insurance-analysis/insurance-analysis-store";

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
            insuranceDocuments: [
              {
                id: "policy-1",
                fileName: "policy.pdf",
                result: {
                  status: "accepted",
                  문자수: 1,
                  문서세션ID: "session-token",
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

describe("Providers", () => {
  it("supplies a QueryClient to children", async () => {
    render(
      <Providers>
        <Probe />
      </Providers>,
    );
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("clears in-memory analysis after leaving the analysis route", async () => {
    navigation.pathname = "/analysis";
    const { rerender } = render(
      <Providers>
        <InsuranceDataProbe />
      </Providers>,
    );

    fireEvent.click(screen.getByRole("button", { name: "seed" }));
    expect(screen.getByText("has-data")).toBeInTheDocument();

    navigation.pathname = "/upload";
    rerender(
      <Providers>
        <InsuranceDataProbe />
      </Providers>,
    );

    await waitFor(() => {
      expect(screen.getByText("empty")).toBeInTheDocument();
    });
  });
});
