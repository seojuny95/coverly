import { useCallback, useState } from "react";

export function useExpandedPolicies() {
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
