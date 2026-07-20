"use client";

import { useId, useState, type ReactNode } from "react";

// Animates via a grid template row rather than max-height so it can expand to
// an intrinsic height without measuring the content.
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
      {/* `inert`, not just `overflow-hidden`: clipping alone leaves collapsed
          links and buttons reachable by keyboard and screen readers. */}
      <div className="overflow-hidden" inert={!expanded}>
        {/* Content needs its own block inside the clipped grid item; with the
            id and clipping on one element the 1fr track measures 0. */}
        <div id={id}>{children}</div>
      </div>
    </div>
  );
}

// For call sites that own their own state; when a parent already tracks it,
// use CollapseRegion alone.
export function useDisclosure() {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  const toggle = () => setExpanded((current) => !current);

  return { expanded, toggle, panelId };
}
