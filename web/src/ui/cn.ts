/**
 * shadcn/ui's `cn` helper, minus its two dependencies.
 *
 * Upstream is `twMerge(clsx(...))`. `clsx` resolves conditional class arguments;
 * `tailwind-merge` resolves *conflicts between Tailwind utilities* — `px-2 px-4` → `px-4`.
 * There are no Tailwind utilities in this repo, so the second half has nothing to do and the
 * first half is fifteen lines. Adding two packages to get those fifteen lines would be the
 * tail wagging the dog.
 */
export type ClassValue = string | number | null | undefined | false | ClassValue[] | { [key: string]: unknown };

export function cn(...inputs: ClassValue[]): string {
  const out: string[] = [];

  const walk = (value: ClassValue): void => {
    if (!value) return;
    if (typeof value === "string" || typeof value === "number") {
      out.push(String(value));
      return;
    }
    if (Array.isArray(value)) {
      for (const item of value) walk(item);
      return;
    }
    for (const [key, enabled] of Object.entries(value)) {
      if (enabled) out.push(key);
    }
  };

  for (const input of inputs) walk(input);
  return out.join(" ");
}
