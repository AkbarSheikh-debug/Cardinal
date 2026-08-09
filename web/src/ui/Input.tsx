/**
 * Input, Label and Field — shadcn's form primitives.
 *
 * Cohere's form treatment is specific and unusually restrained: rectangular inputs with a thin
 * grey border and a *violet* focus ring (`form-focus: #9b60aa`), not the blue used for keyboard
 * focus elsewhere. Both are honoured — `:focus-visible` gets the blue ring the rest of the
 * product uses, and the input's own border turns violet — because they are answering different
 * questions ("where is the keyboard" vs "which field is live").
 *
 * `Field` is the label+control+hint grouping every form in this repo hand-rolls today. It wires
 * `htmlFor`/`id`/`aria-describedby` from one `id`, which is the part that gets forgotten.
 */
import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "./cn";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return <input data-slot="input" type={type} className={cn("ui-input", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn("ui-input ui-textarea", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select data-slot="select" className={cn("ui-input ui-select", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label data-slot="label" className={cn("ui-label", className)} {...props} />;
}

export function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  /** Receives the generated ids, so the control it renders is wired up without the caller doing it. */
  children: (ids: { id: string; describedBy: string | undefined }) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div data-slot="field" className={cn("ui-field", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children({ id, describedBy })}
      {hint && !error && (
        <p id={hintId} className="ui-field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="ui-field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
