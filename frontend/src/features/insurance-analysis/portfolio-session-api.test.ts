import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createPortfolioSession,
  deletePortfolioSession,
  refreshPortfolioSession,
} from "./portfolio-session-api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("portfolio session API", () => {
  it("creates one server-side portfolio session", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          portfolioSessionToken: "portfolio-token",
          expiresAt: "2026-07-18T10:00:00Z",
        }),
        { status: 200 },
      ),
    );

    await expect(createPortfolioSession()).resolves.toMatchObject({
      portfolioSessionToken: "portfolio-token",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/portfolio/sessions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("refreshes and deletes the same bearer token", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            portfolioSessionToken: "next-token",
            expiresAt: "2026-07-18T10:00:00Z",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "deleted" }), { status: 200 }),
      );

    await refreshPortfolioSession("current-token");
    await deletePortfolioSession("next-token");

    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      body: JSON.stringify({ portfolioSessionToken: "current-token" }),
    });
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      body: JSON.stringify({ portfolioSessionToken: "next-token" }),
    });
  });
});
