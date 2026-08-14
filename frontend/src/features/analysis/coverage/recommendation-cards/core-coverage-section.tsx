import type { ReactNode } from "react";

import { cardVariants } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";

export function CoreCoverageSection({
  title,
  description,
  status,
  children,
}: {
  title: string;
  description: string;
  status: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={cn(cardVariants({ variant: "muted" }), "p-5")}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h4 className="text-lg font-semibold tracking-[-0.03em] text-zinc-950">
            {title}
          </h4>
          <p className="mt-2 text-sm leading-6 text-zinc-600">{description}</p>
        </div>
        {status}
      </div>

      {children}
    </section>
  );
}
