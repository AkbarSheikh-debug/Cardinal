"""Exit gate for PHASE 6 -- GENERATIVE-UI.

    python scripts/gate_phase6.py

6.1, 6.3-6.7, 6.9 are pure/deterministic Python -- no container, no `ANTHROPIC_API_KEY`, same
convention D-015 established for gate 3 and gate 5. 6.2 needs `web/`'s npm dependencies and a
Chromium build (`npm install && npx playwright install chromium`, both inside `web/`); when
they are not present this criterion reports `PENDING` rather than failing the whole gate, the
same convention gate 1.10/3.2/4.1 use for a heavy optional prerequisite -- once they *are*
present (as they are on this machine), it is a hard `PASS`/`FAIL`. 6.8 is a static source scan.
6.10 (`[SCALE]` reduced-motion/focus-visible) is not built -- PHASE-6 SS7's own table marks it
`[SCALE]`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.gate_common import REPO_ROOT, Gate, Pending, run_command

WEB_DIR = REPO_ROOT / "web"
WEB_SRC = WEB_DIR / "src"
POWERTRAIN_DIR = WEB_DIR / "public" / "models" / "powertrain"

MAX_MODEL_BYTES = 2 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 16 * 1024 * 1024

#: PHASE-6 SS5 / src/domain/enums.py:PowertrainArchetype -- eight, finite, closed.
EXPECTED_ARCHETYPES = (
    "i3_turbo",
    "i4_na",
    "i4_turbo",
    "v6",
    "v8",
    "hybrid",
    "phev",
    "bev_skateboard",
)


def build_gate() -> Gate:
    gate = Gate(6, "GENERATIVE-UI -- A2UI catalog, compiler, transport, escape hatch")

    # -- 6.1 [MVP] -------------------------------------------------------------------------
    @gate.criterion("6.1", "Every message the compiler emits validates against the catalog schema")
    def _() -> str:
        from src.mcp.ui.compiler import (
            compile_detail_surface,
            compile_progress_surface,
            compile_results_surface,
            compile_score_breakdown_surface,
            compile_tco_breakdown_surface,
            compile_tco_surface,
        )
        from src.mcp.ui.messages import PROTOCOL_VERSION
        from src.mcp.ui.surfaces import SurfaceRegistry
        from src.mcp.ui.validate import validate_component_tree

        registry = SurfaceRegistry()
        compiled_surfaces = [
            compile_progress_surface(
                {"completed_slots": ["goal"], "open_slots": ["budget"]}, phase="interview"
            ),
            compile_results_surface(
                {
                    "weights": {"budget_fit": 1.0},
                    "items": [
                        {
                            "source": "mock_autobazaar",
                            "source_id": "AB-1",
                            "rank": 1,
                            "score": 0.9,
                            "rationale": "cheapest",
                        }
                    ],
                }
            ),
            compile_detail_surface(
                {"source": "mock_autobazaar", "source_id": "AB-1"},
                headline="2022 Toyota GR86",
                price_display="EUR 28,500",
            ),
            compile_tco_surface(
                {
                    "horizon_months": 12,
                    "items": [
                        {"source": "mock_autobazaar", "source_id": "AB-1", "total_cost_eur": 1000.0}
                    ],
                }
            ),
        ]
        from src.domain.money import Money
        from src.domain.scoring import CriterionScore, ScoreBreakdown
        from src.domain.tco import TcoComparison, TcoEstimate, TcoLine, TcoLineKind, TcoPath

        comparison = TcoComparison(
            buy=TcoEstimate(
                path=TcoPath.BUY,
                horizon_months=12,
                lines=(TcoLine(kind=TcoLineKind.PURCHASE, amount=Money.of("10000")),),
                total=Money.of("10000"),
            ),
            rent=TcoEstimate(
                path=TcoPath.RENT,
                horizon_months=12,
                lines=(TcoLine(kind=TcoLineKind.RENTAL, amount=Money.of("6000")),),
                total=Money.of("6000"),
            ),
            break_even_month=None,
        )
        compiled_surfaces.append(
            compile_tco_breakdown_surface(comparison, source="mock_autobazaar", source_id="AB-1")
        )

        compiled_surfaces.append(
            compile_score_breakdown_surface(
                ScoreBreakdown(
                    criteria=(
                        CriterionScore(
                            criterion="budget_fit",
                            weight=1.0,
                            normalised_value=0.5,
                            contribution=0.5,
                        ),
                    ),
                    total=0.5,
                ),
                source="mock_autobazaar",
                source_id="AB-1",
            )
        )

        message_count = 0
        for compiled in compiled_surfaces:
            errors = validate_component_tree(compiled.components)
            assert not errors, f"{compiled.kind} failed validation: {errors}"
            from src.mcp.ui.compiler import to_messages

            for message in to_messages("gate61-session", compiled, registry):
                assert message["version"] == PROTOCOL_VERSION
                message_count += 1

        return (
            f"{len(compiled_surfaces)} compiled surfaces, {message_count} wire messages, "
            f"0 validation errors"
        )

    # -- 6.2 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.2", "Golden-message fixtures render in a headless browser with zero console errors"
    )
    def _() -> str:
        playwright_bin = WEB_DIR / "node_modules" / ".bin" / "playwright"
        playwright_cmd = WEB_DIR / "node_modules" / ".bin" / "playwright.cmd"
        if not (playwright_bin.exists() or playwright_cmd.exists()):
            raise Pending(
                "web/node_modules not installed -- run `npm install` and "
                "`npx playwright install chromium` inside web/"
            )
        import shutil

        npx = shutil.which("npx")
        assert npx is not None, "npx not found on PATH"
        result = run_command([npx, "playwright", "test", "--reporter=line"], cwd=WEB_DIR)
        output = (result.stdout or "") + (result.stderr or "")
        assert result.returncode == 0, f"playwright test failed:\n{output[-4000:]}"
        match = re.search(r"(\d+) passed", output)
        assert match, f"could not find a pass count in playwright output:\n{output[-2000:]}"
        return f"{match.group(0)} (web/tests/render.spec.ts, one test per golden fixture)"

    # -- 6.3 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.3",
        "compose_surface with an unknown component is rejected; the error reaches the model "
        "as a tool result; nothing is forwarded to the renderer",
    )
    def _() -> str:
        import asyncio

        from src.mcp.ui.server import build_ui_server
        from src.mcp.ui.sink import NullUISink
        from tests.conftest import call_mcp_tool

        async def run() -> str:
            sink = NullUISink()
            config = build_ui_server(audience="model", session_id="gate63", sink=sink)
            result = await call_mcp_tool(
                config["instance"],
                "compose_surface",
                {"tree": {"components": [{"id": "root", "component": "NotInTheCatalog"}]}},
            )
            assert result.isError, "an unknown component was not rejected"
            assert "UNKNOWN_COMPONENT" in result.content[0].text
            assert not sink.pushed, "a rejected tree was forwarded to the renderer"
            return result.content[0].text

        text = asyncio.run(run())
        return f"rejected as a tool result, nothing pushed to the sink: {text!r}"

    # -- 6.4 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.4",
        "compose_surface with a dangling child reference, a duplicate id, and depth > 8 are "
        "each rejected",
    )
    def _() -> str:
        from src.mcp.ui.catalog import MAX_TREE_DEPTH
        from src.mcp.ui.validate import validate_component_tree

        dangling = validate_component_tree([{"id": "root", "component": "Card", "child": "ghost"}])
        assert any(e.code == "DANGLING_CHILD" for e in dangling)

        duplicate = validate_component_tree(
            [
                {"id": "root", "component": "Text", "text": "a"},
                {"id": "root", "component": "Text", "text": "b"},
            ]
        )
        assert any(e.code == "DUPLICATE_ID" for e in duplicate)

        chain_ids = ["root"] + [f"n{i}" for i in range(1, MAX_TREE_DEPTH)] + ["leaf"]
        deep_components = [
            {"id": chain_ids[i], "component": "Card", "child": chain_ids[i + 1]}
            for i in range(len(chain_ids) - 1)
        ]
        deep_components.append({"id": "leaf", "component": "Text", "text": "hi"})
        deep = validate_component_tree(deep_components)
        assert any(e.code == "DEPTH_EXCEEDED" for e in deep)

        return (
            f"DANGLING_CHILD, DUPLICATE_ID, and DEPTH_EXCEEDED (depth {len(chain_ids)} > "
            f"{MAX_TREE_DEPTH}) each independently rejected"
        )

    # -- 6.5 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.5", "Action round-trip: a simulated click reaches the agent session with full provenance"
    )
    def _() -> str:
        from fastapi.testclient import TestClient

        from src.agent.orchestrator import CardinalOrchestrator
        from src.api.main import app

        with TestClient(app) as client:
            session_id = "gate65"
            response = client.post(
                f"/sessions/{session_id}/actions",
                json={
                    "surface": f"{session_id}:results",
                    "component": "card-0",
                    "action": "explain",
                    "payload": {"sourceId": "AB-1"},
                },
            )
            assert response.status_code == 200
            orchestrator: CardinalOrchestrator = app.state.orchestrator
            recorded = orchestrator.actions_for(session_id)
            assert len(recorded) == 1
            assert recorded[0]["provenance"] == {
                "surface": f"{session_id}:results",
                "component": "card-0",
                "action": "explain",
                "payload": {"sourceId": "AB-1"},
            }
        return f"provenance recorded in the session's action inbox: {recorded[0]['provenance']}"

    # -- 6.6 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.6",
        "Surface identity is stable -- a second render_results in the same session updates, "
        "does not recreate",
    )
    def _() -> str:
        import asyncio

        from src.mcp.ui.server import build_ui_server
        from src.mcp.ui.sink import NullUISink
        from tests.conftest import call_mcp_tool

        async def run() -> tuple[int, int]:
            sink = NullUISink()
            config = build_ui_server(audience="model", session_id="gate66", sink=sink)
            args = {
                "weights": {"budget_fit": 1.0},
                "items": [
                    {
                        "source": "mock_autobazaar",
                        "source_id": "AB-1",
                        "rank": 1,
                        "score": 0.9,
                        "rationale": "first pass",
                    }
                ],
            }
            await call_mcp_tool(config["instance"], "render_results", args)
            first_creates = sum(1 for m in sink.pushed if "createSurface" in m)
            args["items"][0]["rationale"] = "re-ranked"
            await call_mcp_tool(config["instance"], "render_results", args)
            second_creates = sum(1 for m in sink.pushed if "createSurface" in m)
            return first_creates, second_creates

        first, second = asyncio.run(run())
        assert first == 1, f"the first render_results call should createSurface once, got {first}"
        assert second == first, "a second render_results call created a new surface"
        return f"createSurface count stayed at {first} across two render_results calls"

    # -- 6.7 [MVP] -------------------------------------------------------------------------
    @gate.criterion("6.7", "All 8 powertrain GLBs are <=2 MB; total asset bundle <=16 MB")
    def _() -> str:
        if not POWERTRAIN_DIR.is_dir():
            raise Pending(
                f"{POWERTRAIN_DIR.relative_to(REPO_ROOT)} does not exist -- run "
                "`python -m scripts.generate_powertrain_assets`"
            )
        sizes: dict[str, int] = {}
        for archetype in EXPECTED_ARCHETYPES:
            glb_path = POWERTRAIN_DIR / f"{archetype}.glb"
            assert glb_path.is_file(), f"missing {glb_path.relative_to(REPO_ROOT)}"
            size = glb_path.stat().st_size
            assert size <= MAX_MODEL_BYTES, f"{archetype}.glb is {size} bytes, over the 2 MB budget"
            sizes[archetype] = size
        total = sum(p.stat().st_size for p in POWERTRAIN_DIR.iterdir() if p.is_file())
        assert total <= MAX_TOTAL_ASSET_BYTES, f"total asset bundle {total} bytes over 16 MB"
        return (
            f"8/8 archetypes present, largest {max(sizes.values())} bytes "
            f"(limit {MAX_MODEL_BYTES}), total bundle {total} bytes (limit {MAX_TOTAL_ASSET_BYTES})"
        )

    # -- 6.8 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.8",
        'Every <model-viewer> has a poster; list contexts use reveal="interaction"',
    )
    def _() -> str:
        # Requires a `src=` attribute so a bare mention in a comment/string (e.g. main.tsx's
        # "registers the <model-viewer> custom element") never counts as real JSX usage.
        tag_pattern = re.compile(r"<model-viewer\s[^>]*?/?>", re.DOTALL)
        checked = 0
        for path in WEB_SRC.rglob("*.tsx"):
            text = path.read_text(encoding="utf-8")
            for tag in tag_pattern.findall(text):
                if "src=" not in tag:
                    continue
                checked += 1
                assert "poster=" in tag, f"{path}: <model-viewer> without a poster attribute"
                assert 'reveal="interaction"' in tag, (
                    f'{path}: <model-viewer> in a list/card context must use reveal="interaction"'
                )
        assert checked >= 1, "no <model-viewer> usage found to check"
        return f'{checked} <model-viewer> usage(s), all carry poster + reveal="interaction"'

    # -- 6.9 [MVP] -------------------------------------------------------------------------
    @gate.criterion(
        "6.9",
        "All A2UI imports are from @a2ui/*/v0_9; exactly one module imports MessageProcessor",
    )
    def _() -> str:
        import_pattern = re.compile(r"""from\s+["\'](@a2ui/[\w-]+(?:/[\w./-]*)?)["\']""")
        message_processor_files: list[Path] = []
        bad_imports: list[str] = []
        source_files = list(WEB_SRC.rglob("*.ts")) + list(WEB_SRC.rglob("*.tsx"))
        for path in source_files:
            text = path.read_text(encoding="utf-8")
            for specifier in import_pattern.findall(text):
                if "/v0_9" not in specifier:
                    bad_imports.append(f"{path.relative_to(REPO_ROOT)}: {specifier!r}")
            if re.search(r"\bMessageProcessor\b", text) and "import" in text:
                if re.search(r"import\s*\{[^}]*\bMessageProcessor\b[^}]*\}", text):
                    message_processor_files.append(path)

        assert not bad_imports, f"non-v0_9 A2UI imports: {bad_imports}"
        assert len(message_processor_files) == 1, (
            f"expected exactly one module importing MessageProcessor, found "
            f"{[str(p.relative_to(REPO_ROOT)) for p in message_processor_files]}"
        )
        return (
            f"{len(source_files)} source files scanned, all @a2ui imports pinned to /v0_9; "
            f"MessageProcessor imported only by "
            f"{message_processor_files[0].relative_to(REPO_ROOT)}"
        )

    # -- 6.10 [SCALE] ------------------------------------------------------------------------
    @gate.criterion(
        "6.10",
        "[SCALE] Reduced-motion honoured; every interactive element has a visible focus state",
    )
    def _() -> str:
        raise Pending("reduced-motion + full a11y pass (PHASE-6 SS7) not built -- [SCALE]")

    return gate


def main(argv: list[str] | None = None) -> int:
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
