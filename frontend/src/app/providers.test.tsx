import { render, screen } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { Providers } from "./providers";

function Probe() {
  const { data } = useQuery({
    queryKey: ["probe"],
    queryFn: () => Promise.resolve("ok"),
  });
  return <span>{data ?? "loading"}</span>;
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
});
