/**
 * shadcn/ui's Button, restyled to Cohere and driven by data attributes instead of utilities.
 *
 * The API is upstream's, deliberately: `variant`, `size`, `asChild`, and a `data-slot="button"`
 * / `data-variant` / `data-size` triple on the rendered element. shadcn v4 emits those
 * attributes *as well as* its utility classes, precisely so a consumer can hang their own CSS
 * off them — this kit keeps the attributes and drops the utilities, which is the same contract
 * seen from the other side.
 *
 * The variant list is Cohere's, not upstream's default:
 *
 * - `default` — the near-black pill. DESIGN.md: "Primary CTAs pill-shaped and near-black on
 *   light surfaces." This is "Request a demo", "Start the interview", "Pay".
 * - `link` — an underlined text action. Cohere renders *most* secondary actions this way
 *   rather than as a second button, which is why it is a first-class variant here.
 * - `outline` — the outlined pill used for taxonomy and filter controls.
 * - `secondary` — soft-stone fill, for actions inside white cards.
 * - `ghost` / `destructive` — carried over from upstream unchanged; both earn their place.
 */
import type { ComponentProps } from "react";
import { cn } from "./cn";
import { Slot } from "./Slot";

export type ButtonVariant = "default" | "secondary" | "outline" | "ghost" | "link" | "destructive" | "inverse";
export type ButtonSize = "sm" | "default" | "lg" | "icon" | "icon-sm";

export type ButtonProps = ComponentProps<"button"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  asChild?: boolean;
};

export function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  type,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn("ui-button", className)}
      // A `<button>` inside a `<form>` defaults to `submit`, which has caused a submit-on-click
      // bug in roughly every codebase that has ever had a form. Only set it when we own the
      // element: `asChild` may be rendering an anchor, and `type="button"` on an `<a>` is junk.
      {...(asChild ? {} : { type: type ?? "button" })}
      {...props}
    />
  );
}
