/**
 * `<model-viewer>` is a custom element registered at runtime by `@google/model-viewer`'s
 * side-effect import (`main.tsx`, `dev/fixture-harness.tsx`), not a typed React component --
 * this is the ambient declaration that lets JSX treat it as a real intrinsic element instead
 * of needing a `@ts-expect-error` at every call site.
 */
import type { DetailedHTMLProps, HTMLAttributes } from "react";

type ModelViewerAttributes = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string;
  poster?: string;
  alt?: string;
  "camera-controls"?: boolean;
  "auto-rotate"?: boolean;
  ar?: boolean;
  "ar-modes"?: string;
  reveal?: "auto" | "interaction" | "manual";
  "shadow-intensity"?: string | number;
  "environment-image"?: string;
};

// React 19 moved the JSX namespace under `React.JSX` -- augmenting the bare global `JSX`
// namespace (the pre-19 way) is silently ignored, so this augments "react" itself instead.
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": ModelViewerAttributes;
    }
  }
}

export {};
