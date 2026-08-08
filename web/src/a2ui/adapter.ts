/**
 * The one file that touches the A2UI package surface directly (PHASE-6 SS3: "when it moves,
 * exactly one file changes"). Every other module imports from here, never from
 * `@a2ui/react/*` or `@a2ui/web_core/*` directly for the pieces re-exported below --
 * `MessageProcessor` in particular is imported nowhere else (gate 6.9).
 *
 * Pinned to the exact `0.9.1` versions in package.json and the `v0_9` import path, per
 * PHASE-6 SS3's own risk note: v0.9 -> v1.0 adds `actionResponse` RPC and
 * `surfaceProperties` additively, but nothing here assumes that yet.
 */
import {
  A2uiSurface,
  MarkdownContext,
  basicCatalog,
  createComponentImplementation,
  type ReactComponentImplementation,
} from "@a2ui/react/v0_9";
import {
  Catalog,
  MessageProcessor,
  type A2uiClientAction,
  type A2uiMessage,
  type SurfaceModel,
} from "@a2ui/web_core/v0_9";

export { A2uiSurface, MarkdownContext, createComponentImplementation };
export type { ReactComponentImplementation, A2uiMessage, A2uiClientAction, SurfaceModel };

export const CATALOG_ID = "cardinal.dev:carCatalog";

const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/**
 * `basicCatalog`'s `Text` component renders through a markdown renderer and warns to the
 * console when none is configured (gate 6.2 -- a warning there is a console warning
 * everywhere else). P6's `[MVP]` scope never asks the model to emit real markdown, so rather
 * than pull in `@a2ui/markdown-it` for formatting nothing uses yet, this is a plain
 * HTML-escaping passthrough -- safe, since every string it sees is our own generated text,
 * never untrusted third-party prose (CONSTITUTION I.4 keeps that away from render paths).
 */
export const plainTextMarkdownRenderer: (markdown: string) => Promise<string> = async (markdown) =>
  markdown.replace(/[&<>"']/g, (c) => HTML_ESCAPES[c] ?? c);

export type ActionListener = (action: A2uiClientAction) => void;

/** `carCatalog` = `basicCatalog`'s components plus ours, registered under one catalog id --
 * a compiled surface (`src/mcp/ui/compiler.py`) freely mixes `Column`/`Card`/`Text` with
 * `CarCard`/`InterviewProgress`/etc. in the same component array, so both sets must resolve
 * under the single `catalogId` every `createSurface` message names.
 */
export function buildCarCatalog(custom: ReactComponentImplementation[]): Catalog<ReactComponentImplementation> {
  return new Catalog(CATALOG_ID, [...basicCatalog.components.values(), ...custom]);
}

export function createProcessor(
  custom: ReactComponentImplementation[],
  onAction: ActionListener,
): MessageProcessor<ReactComponentImplementation> {
  const catalog = buildCarCatalog(custom);
  const processor = new MessageProcessor([catalog], onAction);
  return processor;
}

export function processMessages(
  processor: MessageProcessor<ReactComponentImplementation>,
  messages: A2uiMessage[],
): void {
  processor.processMessages(messages);
}
