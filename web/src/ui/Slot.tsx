/**
 * `asChild`, without Radix.
 *
 * Every shadcn component takes `asChild` so a `<Button>` can *be* a `<Link>` rather than wrap
 * one — which matters for accessibility (a link that renders as a button is announced wrong)
 * and for this app in particular, where the showroom's primary CTA is a route change.
 *
 * Upstream delegates to `radix-ui`'s `Slot`. Radix's version also merges refs and composes
 * event handlers across an arbitrary tree; this one merges `className`, `style` and props onto
 * a single child, which is the whole of what the kit below asks of it. The narrower contract
 * is stated rather than implied: `asChild` here expects exactly one React element child.
 */
import { Children, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { cn } from "./cn";

type SlotProps = { children?: ReactNode } & Record<string, unknown>;

export function Slot({ children, ...slotProps }: SlotProps): ReactElement | null {
  if (!isValidElement(children)) {
    // A single element is the contract. Failing loudly beats rendering a button that silently
    // lost its variant, its data-slot and its click handler.
    if (children != null && Children.count(children) > 1) {
      throw new Error("Slot expects a single React element child when `asChild` is set.");
    }
    return null;
  }

  const child = children as ReactElement<Record<string, unknown>>;
  const childProps = child.props;

  return cloneElement(child, {
    ...slotProps,
    ...childProps,
    // The slot's own class and style come first so the child can still override, but both are
    // *merged* rather than replaced — losing `data-variant`'s styling because a caller passed
    // their own className is the classic asChild bug.
    className: cn(slotProps.className as string, childProps.className as string),
    style: { ...(slotProps.style as object), ...(childProps.style as object) },
  });
}
