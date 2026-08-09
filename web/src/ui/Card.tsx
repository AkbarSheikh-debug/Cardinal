/**
 * shadcn/ui's Card family, kept whole.
 *
 * The seven-part anatomy — Card / Header / Title / Description / Action / Content / Footer — is
 * the single most reusable idea in the library, and it is worth porting exactly rather than
 * collapsing into "a div with a border". `CardAction` in particular is the part everyone
 * reinvents badly: a control pinned to the top-right of the header without knocking the title
 * out of alignment.
 *
 * `variant` is this kit's addition, and it is where Cohere enters. DESIGN.md describes several
 * genuinely different card surfaces, and flattening them into one would lose the system:
 *
 * - `default` — white, hairline-bordered, flat.
 * - `stone` — soft-stone `product-card`, 32px padding, used for model/product summaries.
 * - `console` — the near-black `agent-console-card` mockup panel.
 * - `field` — the deep-green `dark-feature-band` surface.
 * - `media` — the 22px-radius `hero-photo-card`, no padding, image bleeds to the corners.
 */
import type { ComponentProps } from "react";
import { cn } from "./cn";

export type CardVariant = "default" | "stone" | "console" | "field" | "media";

export function Card({
  className,
  variant = "default",
  ...props
}: ComponentProps<"div"> & { variant?: CardVariant }) {
  return <div data-slot="card" data-variant={variant} className={cn("ui-card", className)} {...props} />;
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-header" className={cn("ui-card-header", className)} {...props} />;
}

export function CardTitle({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-title" className={cn("ui-card-title", className)} {...props} />;
}

export function CardDescription({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-description" className={cn("ui-card-description", className)} {...props} />;
}

/** Sits top-right of the header without disturbing the title's baseline. */
export function CardAction({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-action" className={cn("ui-card-action", className)} {...props} />;
}

export function CardContent({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("ui-card-content", className)} {...props} />;
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-footer" className={cn("ui-card-footer", className)} {...props} />;
}
