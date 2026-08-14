import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { useDialogA11y } from "./use-dialog-a11y";

function TestDialog({
  autoFocus,
  trapFocus,
}: {
  autoFocus?: boolean;
  trapFocus?: boolean;
}) {
  const [open, setOpen] = useState(true);
  const onClose = vi.fn(() => setOpen(false));
  const dialogRef = useDialogA11y<HTMLDivElement>({
    open,
    onClose,
    autoFocus,
    trapFocus,
  });

  if (!open) return <p>closed</p>;

  return (
    <div ref={dialogRef} role="dialog" aria-modal tabIndex={-1}>
      <button type="button">first</button>
      <button type="button">last</button>
    </div>
  );
}

describe("useDialogA11y", () => {
  it("closes on Escape", () => {
    render(<TestDialog />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByText("closed")).toBeInTheDocument();
  });

  it("auto-focuses the first focusable element by default", () => {
    render(<TestDialog />);
    expect(screen.getByText("first")).toHaveFocus();
  });

  it("does not steal focus when autoFocus is false", () => {
    render(
      <div>
        <input aria-label="outside" />
        <TestDialog autoFocus={false} />
      </div>,
    );
    const outside = screen.getByLabelText("outside");
    outside.focus();
    expect(outside).toHaveFocus();
  });

  it("wraps Tab from the last element back to the first", () => {
    render(<TestDialog />);
    screen.getByText("last").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByText("first")).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element back to the last", () => {
    render(<TestDialog />);
    screen.getByText("first").focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByText("last")).toHaveFocus();
  });

  it("does not trap Tab when trapFocus is false (non-modal panel)", () => {
    render(
      <div>
        <TestDialog trapFocus={false} />
        <button type="button">outside</button>
      </div>,
    );
    screen.getByText("last").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    // No preventDefault was called, so focus stays wherever it was — the
    // hook does not force it back to "first".
    expect(screen.getByText("last")).toHaveFocus();
  });
});
