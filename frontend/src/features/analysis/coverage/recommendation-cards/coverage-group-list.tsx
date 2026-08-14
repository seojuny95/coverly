import { Card } from "@/shared/components/ui/card";

import type { CoverageGroup } from "../api";
import { formatKoreanWon } from "../money-format";

export function CoverageGroupList({
  groups,
  fallbackNames,
  emptyNotice,
}: {
  groups: CoverageGroup[];
  fallbackNames: string[];
  emptyNotice?: string;
}) {
  if (groups.length === 0) {
    if (fallbackNames.length === 0) {
      if (!emptyNotice) return null;
      return (
        <p className="mt-4 text-xs leading-5 text-zinc-500">{emptyNotice}</p>
      );
    }
    return (
      <p className="mt-4 text-xs leading-5 text-blue-700">
        확인된 담보: {fallbackNames.join(" · ")}
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-2">
      <p className="text-xs font-semibold text-zinc-500">확인된 담보</p>
      {groups.map((group) => (
        <Card
          key={group.label}
          className={`rounded-xl px-3 py-2 text-xs leading-5 ${coverageGroupClassName(group.tone)}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold">{group.label}</p>
            <span>
              {typeof group.total_amount === "number"
                ? `합계 ${formatKoreanWon(group.total_amount)}`
                : `${group.coverage_names?.length ?? 0}개`}
            </span>
          </div>
          <p className="mt-1">{group.coverage_names?.join(" · ")}</p>
          <p className="mt-1 opacity-80">{group.detail}</p>
        </Card>
      ))}
    </div>
  );
}

function coverageGroupClassName(tone: CoverageGroup["tone"]) {
  switch (tone) {
    case "confirmed":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "review":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "limited":
      return "border-zinc-200 bg-zinc-100 text-zinc-700";
  }
}

export function CoverageNamesNotice({ names }: { names: string[] }) {
  if (names.length === 0) {
    return (
      <p className="mt-4 text-xs leading-5 text-zinc-500">
        현재 업로드된 보험증권에서는 해당 보장이 확인되지 않아요
      </p>
    );
  }

  return (
    <p className="mt-4 text-xs leading-5 text-blue-700">
      확인된 담보: {names.join(" · ")}
    </p>
  );
}
