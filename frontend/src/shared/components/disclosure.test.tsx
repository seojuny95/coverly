import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { CollapseRegion } from "./disclosure";

describe("CollapseRegion", () => {
  test("marks collapsed content inert and expanded content interactive", () => {
    const { rerender } = render(
      <CollapseRegion expanded={false}>
        <p>패널 내용</p>
      </CollapseRegion>,
    );

    expect(screen.getByText("패널 내용").closest("[inert]")).not.toBeNull();

    rerender(
      <CollapseRegion expanded={true}>
        <p>패널 내용</p>
      </CollapseRegion>,
    );

    expect(screen.getByText("패널 내용").closest("[inert]")).toBeNull();
  });
});
