/**
 * Tabs — shadcn's API (`Tabs` / `TabsList` / `TabsTrigger` / `TabsContent`), Radix's keyboard
 * behaviour, no dependency on either.
 *
 * The showroom's facet rail is the reason this exists rather than five buttons and a
 * `useState`. Five buttons with a `useState` would render a control that looks like tabs,
 * announces itself as a toolbar, and traps a keyboard user in a five-stop tab sequence. The
 * WAI-ARIA tabs pattern that Radix implements is the thing being borrowed here:
 *
 * - `role="tablist"` / `role="tab"` / `role="tabpanel"`, with `aria-controls` both ways.
 * - **Roving tabindex**: the tablist is one tab stop; arrows move between tabs.
 * - Arrow keys follow `orientation`, so a vertical rail responds to ↑/↓ and not ←/→.
 * - `Home`/`End` jump to the ends.
 *
 * Selection is automatic (moving focus activates), which is correct when panels are already in
 * the document and cheap to show — as they are here.
 */
import {
  createContext,
  useCallback,
  useContext,
  useId,
  useRef,
  useState,
  type ComponentProps,
  type KeyboardEvent,
} from "react";
import { cn } from "./cn";

type TabsContextValue = {
  value: string;
  setValue: (next: string) => void;
  baseId: string;
  orientation: "horizontal" | "vertical";
};

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabs(component: string): TabsContextValue {
  const context = useContext(TabsContext);
  if (!context) throw new Error(`<${component}> must be rendered inside <Tabs>`);
  return context;
}

export function Tabs({
  value: controlledValue,
  defaultValue,
  onValueChange,
  orientation = "horizontal",
  className,
  children,
  ...props
}: Omit<ComponentProps<"div">, "onChange"> & {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  orientation?: "horizontal" | "vertical";
}) {
  const [uncontrolled, setUncontrolled] = useState(defaultValue ?? "");
  const baseId = useId();
  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : uncontrolled;

  const setValue = useCallback(
    (next: string) => {
      if (!isControlled) setUncontrolled(next);
      onValueChange?.(next);
    },
    [isControlled, onValueChange],
  );

  return (
    <TabsContext.Provider value={{ value, setValue, baseId, orientation }}>
      <div data-slot="tabs" data-orientation={orientation} className={cn("ui-tabs", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, children, ...props }: ComponentProps<"div">) {
  const { orientation } = useTabs("TabsList");
  const listRef = useRef<HTMLDivElement>(null);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = orientation === "vertical" ? "ArrowDown" : "ArrowRight";
    const previous = orientation === "vertical" ? "ArrowUp" : "ArrowLeft";
    if (!["Home", "End", next, previous].includes(event.key)) return;

    const tabs = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])') ?? [],
    );
    if (tabs.length === 0) return;

    const current = tabs.indexOf(document.activeElement as HTMLButtonElement);
    let index: number;
    if (event.key === "Home") index = 0;
    else if (event.key === "End") index = tabs.length - 1;
    // Wrapping, per the ARIA pattern: ↓ on the last tab returns to the first.
    else if (event.key === next) index = (current + 1) % tabs.length;
    else index = (current - 1 + tabs.length) % tabs.length;

    event.preventDefault();
    tabs[index].focus();
    tabs[index].click();
  };

  return (
    <div
      ref={listRef}
      data-slot="tabs-list"
      data-orientation={orientation}
      role="tablist"
      aria-orientation={orientation}
      onKeyDown={onKeyDown}
      className={cn("ui-tabs-list", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  className,
  ...props
}: ComponentProps<"button"> & { value: string }) {
  const { value: active, setValue, baseId } = useTabs("TabsTrigger");
  const selected = active === value;

  return (
    <button
      type="button"
      role="tab"
      id={`${baseId}-tab-${value}`}
      aria-controls={`${baseId}-panel-${value}`}
      aria-selected={selected}
      // Roving tabindex: only the active tab is in the page's tab order.
      tabIndex={selected ? 0 : -1}
      data-slot="tabs-trigger"
      data-state={selected ? "active" : "inactive"}
      onClick={() => setValue(value)}
      className={cn("ui-tabs-trigger", className)}
      {...props}
    />
  );
}

export function TabsContent({
  value,
  className,
  children,
  ...props
}: ComponentProps<"div"> & { value: string }) {
  const { value: active, baseId } = useTabs("TabsContent");
  const selected = active === value;

  return (
    <div
      role="tabpanel"
      id={`${baseId}-panel-${value}`}
      aria-labelledby={`${baseId}-tab-${value}`}
      hidden={!selected}
      // A panel is a tab stop so a keyboard user can reach its content after selecting it.
      tabIndex={selected ? 0 : -1}
      data-slot="tabs-content"
      data-state={selected ? "active" : "inactive"}
      className={cn("ui-tabs-content", className)}
      {...props}
    >
      {selected ? children : null}
    </div>
  );
}
