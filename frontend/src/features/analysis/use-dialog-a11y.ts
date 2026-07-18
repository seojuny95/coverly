"use client";

import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  );
}

// Shared keyboard behavior for modal dialogs: Escape closes, Tab/Shift+Tab
// cycles focus within the dialog instead of escaping to the page behind it.
// Attach the returned ref to the dialog's outer element.
export function useDialogA11y<T extends HTMLElement>({
  open,
  onClose,
  autoFocus = true,
  trapFocus = true,
}: {
  open: boolean;
  onClose: () => void;
  // Set false when the caller already moves focus itself on open (e.g. to a
  // specific input) — avoids fighting over which element gets focus first.
  autoFocus?: boolean;
  // Set false for a non-modal (aria-modal="false") floating panel, where the
  // page behind it stays interactive — trapping Tab there would block the
  // user from tabbing back out to it.
  trapFocus?: boolean;
}) {
  const dialogRef = useRef<T>(null);

  useEffect(() => {
    if (!open) return;

    const dialog = dialogRef.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    if (autoFocus && dialog && !dialog.contains(document.activeElement)) {
      const [firstFocusable] = focusableElements(dialog);
      (firstFocusable ?? dialog).focus();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (!trapFocus || event.key !== "Tab" || !dialog) return;

      const elements = focusableElements(dialog);
      if (elements.length === 0) return;

      const first = elements[0];
      const last = elements[elements.length - 1];
      const active = document.activeElement;

      if (event.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open, onClose, autoFocus, trapFocus]);

  return dialogRef;
}
