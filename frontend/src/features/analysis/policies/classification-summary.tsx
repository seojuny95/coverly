import { CircleHelp } from "lucide-react";

import { POLICY_CLASSIFICATION_DESCRIPTIONS } from "./classification";
import type { AnalyzedInsurance } from "../session/store";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { POLICY_CLASSIFICATIONS } from "@/shared/api/generated-runtime";

export function PolicyClassificationSummary({
  groupedDocuments,
}: {
  groupedDocuments: Record<string, AnalyzedInsurance[]>;
}) {
  return (
    <dl className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {POLICY_CLASSIFICATIONS.map((classification) => (
        <div
          key={classification}
          className="relative rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-[4px_4px_0_#f4f4f5]"
        >
          <dt className="flex items-start justify-between gap-2 text-xs font-medium text-zinc-500">
            <span>{classification}</span>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={`${classification} 설명`}
                  className="inline-flex size-6 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                >
                  <CircleHelp aria-hidden="true" className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                align="end"
                sideOffset={4}
                className="max-w-64 px-3 py-2 text-left text-xs leading-5 font-normal"
              >
                {POLICY_CLASSIFICATION_DESCRIPTIONS[classification]}
              </TooltipContent>
            </Tooltip>
          </dt>
          <dd className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-blue-600">
            {groupedDocuments[classification]?.length ?? 0}
          </dd>
        </div>
      ))}
    </dl>
  );
}
