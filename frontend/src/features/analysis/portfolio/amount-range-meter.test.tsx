import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AmountRangeMeter } from "./amount-range-meter";

const formatAmount = (amount: number) => `${amount.toLocaleString("ko-KR")}원`;

describe("AmountRangeMeter", () => {
  it("places an unconfirmed amount at zero without presenting it as a confirmed zero", () => {
    render(
      <AmountRangeMeter
        current={null}
        referenceMin={10_000_000}
        referenceMax={20_000_000}
        formatAmount={formatAmount}
      />,
    );

    const progressbar = screen.getByRole("progressbar", {
      name: "현재 금액",
    });

    expect(progressbar).toHaveAttribute("aria-valuenow", "0");
    expect(progressbar).toHaveAttribute("aria-valuetext", "미확인");
    expect(progressbar).toHaveStyle("--amount-range-position: 0%");
  });

  it("keeps a boundary reference arrow at its actual percentage", () => {
    const { container } = render(
      <AmountRangeMeter
        current={20}
        referenceMin={1}
        referenceMax={20}
        referenceLabel="권장"
        formatAmount={formatAmount}
      />,
    );

    const arrows = container.querySelectorAll(
      '[data-slot="amount-range-reference-arrow"]',
    );

    expect(arrows).toHaveLength(2);
    expect(arrows[0]).toHaveStyle("left: 2%");
  });
});
