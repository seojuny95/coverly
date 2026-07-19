import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/shared/lib/utils";

// Faithful to the app's established card language: a zinc-bordered white surface
// with the signature hard-offset shadow. Padding stays with the caller since it
// varies widely across usages.
const cardVariants = cva("rounded-2xl border text-left", {
  variants: {
    variant: {
      default: "border-zinc-200 bg-white",
      muted: "border-zinc-200 bg-zinc-50",
      dashed: "border-dashed border-zinc-200 bg-white",
    },
    shadow: {
      none: "",
      mist: "shadow-[5px_5px_0_#e8edff]",
      zinc: "shadow-[5px_5px_0_#f4f4f5]",
    },
  },
  defaultVariants: {
    variant: "default",
    shadow: "none",
  },
});

function Card({
  className,
  variant,
  shadow,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof cardVariants>) {
  return (
    <div
      data-slot="card"
      className={cn(cardVariants({ variant, shadow }), className)}
      {...props}
    />
  );
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn(
        "font-heading text-base leading-snug font-medium text-zinc-950",
        className,
      )}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-zinc-500", className)}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={className} {...props} />;
}

export { Card, CardTitle, CardDescription, CardContent, cardVariants };
