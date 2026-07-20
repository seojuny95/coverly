"use client";

import { useCallback, useId, useState, type ReactNode } from "react";

/**
 * Controlled animated show/hide region shared by every accordion-style
 * disclosure in the app. The height transition drives off a CSS grid
 * template row so it can animate to/from an intrinsic (unmeasured) height.
 */
export function CollapseRegion({
  expanded,
  id,
  children,
}: {
  expanded: boolean;
  id?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${
        expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
      }`}
    >
      {/* `inert` (not just `overflow-hidden`) is required: clipping alone
          still leaves collapsed focusable children keyboard/AT-reachable. */}
      <div className="overflow-hidden" inert={!expanded}>
        <div id={id}>{children}</div>
      </div>
    </div>
  );
}

/** For call sites that own their own expanded/collapsed state. */
export function useDisclosure() {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();

  const toggle = useCallback(() => {
    setExpanded((current) => !current);
  }, []);

  return { expanded, toggle, panelId };
}
