"use client";

import { LoaderCircle } from "lucide-react";
import type { ComponentProps } from "react";

import { Button } from "./ui/button";

type RetryButtonProps = Omit<ComponentProps<typeof Button>, "children"> & {
  isPending: boolean;
  label: string;
  pendingLabel: string;
};

export function RetryButton({
  isPending,
  label,
  pendingLabel,
  disabled,
  ...props
}: RetryButtonProps) {
  return (
    <Button {...props} disabled={disabled || isPending} aria-busy={isPending}>
      {isPending ? (
        <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
      ) : null}
      {isPending ? pendingLabel : label}
    </Button>
  );
}
