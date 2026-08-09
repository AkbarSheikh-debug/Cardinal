/**
 * Separator — the hairline rule.
 *
 * Small component, load-bearing system idea. Cohere is "mostly flat … depth comes from surface
 * alternation, media contrast, rounded corners and thin borders rather than drop shadows", and
 * its research/editorial surfaces are built out of rule-separated rows rather than cards. A
 * shared rule with one colour is what keeps that from drifting into five slightly different
 * greys.
 *
 * `decorative` follows shadcn/Radix: a rule that only groups things visually is hidden from the
 * accessibility tree, and one that genuinely separates sections announces itself.
 */
import type { ComponentProps } from "react";
import { cn } from "./cn";

export function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: ComponentProps<"div"> & { orientation?: "horizontal" | "vertical"; decorative?: boolean }) {
  return (
    <div
      data-slot="separator"
      data-orientation={orientation}
      role={decorative ? "none" : "separator"}
      aria-orientation={decorative ? undefined : orientation}
      className={cn("ui-separator", className)}
      {...props}
    />
  );
}
