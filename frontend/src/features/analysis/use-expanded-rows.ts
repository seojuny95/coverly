import { useCallback, useState } from "react";

// Tracks which rows are expanded by id. Extracted from the analysis screen so
// the Set bookkeeping stays out of the render body.
export function useExpandedRows() {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  const isExpanded = useCallback(
    (id: string) => expandedIds.has(id),
    [expandedIds],
  );

  const toggle = useCallback((id: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  return { isExpanded, toggle };
}
