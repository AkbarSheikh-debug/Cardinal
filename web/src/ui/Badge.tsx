/**
 * shadcn/ui's Badge, with Cohere's taxonomy chips added.
 *
 * `coral` is the one that matters: DESIGN.md makes coral chips a *hero-level* control on
 * editorial surfaces ("Typography is oversized relative to typical filters"), and it is
 * explicit that coral must not spread beyond taxonomy into the CTA system. Giving it its own
 * variant is how that stays true — the rule lives in one place instead of in everyone's memory.
 *
 * `mono` renders the uppercase technical label Cohere uses for system markers, which is exactly
 * what this product's phase names, availability states and tier labels are.
 */
import type { ComponentProps } from "react";
import { cn } from "./cn";
import { Slot } from "./Slot";

export type BadgeVariant = "default" | "secondary" | "outline" | "coral" | "mono" | "success" | "destructive";

export function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: ComponentProps<"span"> & { variant?: BadgeVariant; asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";
  return (
    <Comp data-slot="badge" data-variant={variant} className={cn("ui-badge", className)} {...props} />
  );
}
