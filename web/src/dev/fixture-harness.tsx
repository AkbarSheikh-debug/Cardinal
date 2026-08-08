/**
 * Gate 6.2's target page: loads one golden-message fixture named by `?fixture=<file>.json`
 * (relative to `web/fixtures/`), feeds it through the real `MessageProcessor` + `carCatalog`,
 * and renders whatever surface results with `A2uiSurface`. Not part of the product UI --
 * `tests/render.spec.ts` is the only thing that ever navigates here, and it asserts zero
 * console errors/warnings while this page loads and renders (CONSTITUTION II.4's validation
 * promise made visible: a golden fixture is, by definition, one the server already accepted).
 */
import "@google/model-viewer";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  A2uiSurface,
  MarkdownContext,
  createProcessor,
  plainTextMarkdownRenderer,
  type ReactComponentImplementation,
  type SurfaceModel,
} from "../a2ui/adapter";
import { customComponents } from "../a2ui/catalog";
import "../styles.css";

function fixtureName(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("fixture") ?? "progress.json";
}

function Harness(): React.ReactElement {
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const processor = createProcessor(customComponents, () => {
      /* the harness never round-trips actions -- it only renders */
    });
    processor.model.onSurfaceCreated.subscribe(() => {
      setSurfaces([...processor.model.surfacesMap.values()]);
    });
    fetch(`/fixtures/${fixtureName()}`)
      .then((r) => r.json())
      .then((messages) => {
        processor.processMessages(messages);
        setSurfaces([...processor.model.surfacesMap.values()]);
      })
      .finally(() => setLoaded(true));
  }, []);

  return (
    <div data-testid="harness-root" data-loaded={loaded}>
      <MarkdownContext.Provider value={plainTextMarkdownRenderer}>
        {surfaces.map((surface) => (
          <section key={surface.id} className="cardinal-surface">
            <A2uiSurface surface={surface} />
          </section>
        ))}
      </MarkdownContext.Provider>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root element not found");
}
createRoot(container).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
