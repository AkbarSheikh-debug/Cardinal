"""Exit gate for PHASE 16 -- VOICE (PLAN-02 P16).

    python scripts/gate_phase16.py

Every criterion runs with the voice environment **scrubbed**, then re-injects a stub provider
where tier 1 needs proving. That is deliberate and worth stating plainly: this gate asserts the
*cascade* behaves, not that ElevenLabs is reachable. A criterion that needed a funded account
could only ever run on one machine, which is the opposite of what a gate is for.

16.1/16.7 need `web/node_modules` + Chromium and report PENDING without them (gate 6.2's
convention).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import anyio
from fastapi.testclient import TestClient

from scripts.gate_common import REPO_ROOT, Gate, Pending, run_command, scan_for_terms
from src.adapters.voice.cascade import DEMO_TRANSCRIPTS, MIN_AUDIO_BYTES, VoiceCascade
from src.adapters.voice.protocol import QuotaExhausted, VoiceError
from src.domain.voice import VoiceTier, select_tier

WEB = REPO_ROOT / "web"

VOICE_ENV = (
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "DEMO_MODE",
)

#: Every voice variable the code actually reads. 16.10 checks each is documented in
#: `.env.example`, which is what stops gate 11.7 going red the next time it runs.
DOCUMENTED_VARS = (
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
)

#: Real key prefixes. If one of these ever appears in source or a lockfile, somebody pasted a
#: live credential -- the exact thing PLAN-02 P16 warns against when reusing another project's
#: keys. This file names them literally and is excluded from its own scan.
KEY_SHAPED_TERMS = (
    "sk_live_",
    "sk-proj-",
    "xi-api-key:",
    "gsk_",
)


@contextmanager
def scrubbed_env() -> Iterator[None]:
    saved = {name: os.environ.pop(name, None) for name in VOICE_ENV}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


class StubSynth:
    def __init__(self, *, fails: Exception | None = None) -> None:
        self._fails = fails

    @property
    def name(self) -> str:
        return "gate-stub"

    def is_configured(self) -> bool:
        return True

    async def speak(self, text: str, *, voice_id: str | None = None) -> bytes:
        if self._fails is not None:
            raise self._fails
        return b"ID3gate-audio"


class StubStt:
    @property
    def name(self) -> str:
        return "gate-stub"

    def is_configured(self) -> bool:
        return True

    async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
        return "a family suv under thirty thousand euros"


def build_gate() -> Gate:
    gate = Gate(16, "VOICE -- three-tier cascade, picker, push-to-talk")

    # -- 16.1 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.1", "all three controls work independently; state survives a reload")
    def _() -> str:
        npx = shutil.which("npx")
        installed = (WEB / "node_modules" / ".bin" / "playwright").exists() or (
            WEB / "node_modules" / ".bin" / "playwright.cmd"
        ).exists()
        if npx is None or not installed:
            raise Pending(
                "web/node_modules not installed -- run `npm install` and "
                "`npx playwright install chromium` inside web/, then re-run"
            )
        result = run_command(
            [npx, "playwright", "test", "--config=playwright.voice.config.ts"], cwd=WEB
        )
        assert result.returncode == 0, (
            f"playwright exited {result.returncode}\n{result.stdout[-2500:]}\n"
            f"{result.stderr[-800:]}"
        )
        report = WEB / "test-results" / "voice.json"
        stats = (
            json.loads(report.read_text(encoding="utf-8")).get("stats", {})
            if report.exists()
            else {}
        )
        return (
            "web/tests/voice.spec.ts passed in a real Chromium -- stats="
            f"{ {k: stats.get(k) for k in ('expected', 'unexpected', 'flaky', 'skipped')} }"
        )

    # -- 16.2 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "16.2", "DEMO_MODE completes a voice turn with every voice env var unset (tier 2)"
    )
    def _() -> str:
        from src.api.main import app

        with scrubbed_env():
            os.environ["DEMO_MODE"] = "true"
            try:
                with TestClient(app) as client:
                    app.state.voice = VoiceCascade()
                    response = client.post(
                        "/voice/transcribe",
                        files={"file": ("speech.webm", b"x" * 10, "audio/webm")},
                        data={"session_id": "gate16"},
                    )
                    assert response.status_code == 200, (
                        f"transcribe returned {response.status_code} with the env unset"
                    )
                    body = response.json()
                    assert body["text"] == DEMO_TRANSCRIPTS[0]
                    assert body["tier"] == VoiceTier.BROWSER.value

                    spoken = client.post("/voice/speak", json={"text": "hello"})
                    assert spoken.status_code == 204, "speak did not hand off to the browser"
            finally:
                os.environ.pop("DEMO_MODE", None)
        return (
            f"transcribe -> 200 tier='browser' text={DEMO_TRANSCRIPTS[0][:38]!r}...; "
            "speak -> 204 (browser speaks); ELEVENLABS/GROQ/OPENAI keys all unset"
        )

    # -- 16.3 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.3", "with a provider wired, a voice turn is served by tier 1")
    def _() -> str:
        from src.api.main import app

        with scrubbed_env(), TestClient(app) as client:
            app.state.voice = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt())
            spoken = client.post("/voice/speak", json={"text": "hello"})
            assert spoken.status_code == 200, f"speak returned {spoken.status_code}"
            assert spoken.headers["X-Voice-Tier"] == VoiceTier.PROVIDER.value

            heard = client.post(
                "/voice/transcribe",
                files={"file": ("speech.webm", b"x" * (MIN_AUDIO_BYTES + 1), "audio/webm")},
            )
            assert heard.status_code == 200
            assert heard.json()["tier"] == VoiceTier.PROVIDER.value
        return (
            "speak -> 200 X-Voice-Tier='provider'; transcribe -> 200 tier='provider' "
            "(stub provider: this asserts tier *selection*, not ElevenLabs reachability)"
        )

    # -- 16.4 [MVP] ---------------------------------------------------------------
    @gate.criterion(
        "16.4", "a mid-session quota error drops to tier 2 without a reload or a dead control"
    )
    def _() -> str:
        from src.api.main import app

        class Flaky(StubSynth):
            def __init__(self) -> None:
                super().__init__()
                self.n = 0

            async def speak(self, text: str, *, voice_id: str | None = None) -> bytes:
                self.n += 1
                if self.n == 2:
                    raise QuotaExhausted("payment_required")
                return b"ID3gate-audio"

        with scrubbed_env(), TestClient(app) as client:
            app.state.voice = VoiceCascade(synthesizer=Flaky(), transcriber=StubStt())
            tiers = []
            for _ in range(3):
                response = client.post("/voice/speak", json={"text": "hi"})
                tiers.append(response.headers["X-Voice-Tier"])
        assert tiers == ["provider", "browser", "provider"], (
            f"the cascade latched instead of choosing per call: {tiers}"
        )
        return (
            f"three consecutive utterances served {tiers} -- the quota failure degraded the "
            "second only; no reload, and tier 1 resumed on the third"
        )

    # -- 16.5 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.5", "a denied mic falls to tier 3 with no turn or phase state lost")
    def _() -> str:
        # Server-side half: `select_tier` is total, so "no provider, no browser" still has an
        # answer. The browser half (a denied `getUserMedia` leaving the composer usable) is
        # asserted by 16.1's spec.
        assert select_tier(provider_ready=False, browser_ready=False) is VoiceTier.TEXT
        from src.api.main import app

        with scrubbed_env(), TestClient(app) as client:
            body = client.get("/voice/capabilities?browser=false").json()
            assert body["speak_tier"] == VoiceTier.TEXT.value
            assert body["transcribe_tier"] == VoiceTier.TEXT.value
        return (
            "select_tier(provider=False, browser=False) -> 'text'; "
            "/voice/capabilities?browser=false reports text for both directions"
        )

    # -- 16.6 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.6", "a TTS failure never blocks or delays the text reply")
    def _() -> str:
        from src.api.main import app

        with scrubbed_env(), TestClient(app) as client:
            app.state.voice = VoiceCascade(
                synthesizer=StubSynth(fails=VoiceError("provider exploded"))
            )
            response = client.post("/voice/speak", json={"text": "hello"})
        # A failure surfaces as "the browser should say this", not as a 5xx the chat rail has
        # to catch -- which is what keeps a dead TTS provider off the reply path entirely.
        assert response.status_code == 204, (
            f"a TTS failure surfaced as {response.status_code}, which the client would treat "
            "as an error rather than a fallback"
        )
        assert response.headers["X-Voice-Tier"] == VoiceTier.BROWSER.value
        return "a raising synthesiser produced 204 X-Voice-Tier='browser', never a 5xx"

    # -- 16.7 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.7", "the transcript is shown for confirmation, never auto-sent")
    def _() -> str:
        from src.api.main import app

        with scrubbed_env():
            os.environ["DEMO_MODE"] = "true"
            try:
                with TestClient(app) as client:
                    app.state.voice = VoiceCascade()
                    client.post(
                        "/voice/transcribe",
                        files={"file": ("speech.webm", b"x" * 10, "audio/webm")},
                        data={"session_id": "gate167"},
                    )
                    recorded = app.state.orchestrator.actions_for("gate167")
            finally:
                os.environ.pop("DEMO_MODE", None)
        assert recorded == [], f"transcribing created {len(recorded)} turn(s) as a side effect"

        # Structural half: no module that can transcribe also reaches the send path.
        client_src = (WEB / "src" / "voice" / "api.ts").read_text(encoding="utf-8")
        assert "postMessage" not in client_src, (
            "web/src/voice/api.ts references postMessage -- a path from the microphone to a "
            "chat turn is exactly what the no-auto-send rule forbids"
        )
        return (
            "transcribe created 0 turns; web/src/voice/api.ts contains no reference to "
            "postMessage, so no code path runs mic -> turn"
        )

    # -- 16.8 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.8", "the picker offers provider voices only when a provider exists")
    def _() -> str:
        # `capabilities` is async now: the voice list comes from the *account* rather than a
        # constant, because hardcoded library voice ids are refused on a free ElevenLabs tier
        # (`paid_plan_required`) -- the failure that had every call silently degrading while
        # this very criterion reported a healthy picker.
        with scrubbed_env():
            without = anyio.run(VoiceCascade().capabilities)
            with_provider = anyio.run(VoiceCascade(synthesizer=StubSynth()).capabilities)
        assert all(v.tier is VoiceTier.BROWSER for v in without.voices)
        assert len(without.voices) == 1, "a keyless deployment offered a voice it cannot play"
        provider_voices = [v for v in with_provider.voices if v.tier is VoiceTier.PROVIDER]
        assert len(provider_voices) >= 2, "the picker needs more than one voice to be a picker"
        return (
            f"no key -> {len(without.voices)} voice ({without.voices[0].label!r}); "
            f"provider wired -> {len(with_provider.voices)} voices, "
            f"{len(provider_voices)} of them tier 1"
        )

    # -- 16.9 [MVP] ---------------------------------------------------------------
    @gate.criterion("16.9", "every voice call records which tier served it, as a span attribute")
    def _() -> str:
        from src.agent.tracing import (
            clear_captured_spans,
            configure_tracing,
            get_captured_spans,
        )
        from src.api.main import app

        configure_tracing()
        clear_captured_spans()
        with scrubbed_env(), TestClient(app) as client:
            app.state.voice = VoiceCascade(synthesizer=StubSynth(), transcriber=StubStt())
            client.post("/voice/speak", json={"text": "hello"})
            client.post(
                "/voice/transcribe",
                files={"file": ("speech.webm", b"x" * (MIN_AUDIO_BYTES + 1), "audio/webm")},
            )

        spans = {
            s.name: dict(s.attributes or {})
            for s in get_captured_spans()
            if s.name in {"voice.speak", "voice.transcribe"}
        }
        assert "voice.speak" in spans and "voice.transcribe" in spans, (
            f"expected both voice spans, captured {sorted(spans)}"
        )
        for name, attrs in spans.items():
            assert attrs.get("voice.tier"), f"{name} carries no voice.tier attribute"
        return (
            f"voice.speak tier={spans['voice.speak']['voice.tier']!r}, "
            f"voice.transcribe tier={spans['voice.transcribe']['voice.tier']!r} -- "
            "'the voice sounded worse today' is falsifiable"
        )

    # -- 16.10 [MVP] --------------------------------------------------------------
    @gate.criterion("16.10", ".env.example documents every voice variable the code reads")
    def _() -> str:
        documented = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        missing = [name for name in DOCUMENTED_VARS if name not in documented]
        assert not missing, f"undocumented voice variables: {missing} (gate 11.7 would go red)"
        return f"{len(DOCUMENTED_VARS)} voice variables, all present in .env.example"

    # -- 16.11 [MVP] --------------------------------------------------------------
    @gate.criterion("16.11", "no provider key value appears in source, deps or either lockfile")
    def _() -> str:
        scanned, hits = scan_for_terms(
            KEY_SHAPED_TERMS,
            scan_dirs=("src", "scripts", "tests"),
            extra_files=("pyproject.toml", "web/package.json", "web/package-lock.json"),
            exclude_files=(Path(__file__).resolve(),),
        )
        assert not hits, "key-shaped strings found:\n  " + "\n  ".join(hits)
        return (
            f"{scanned} files scanned for {len(KEY_SHAPED_TERMS)} live-credential prefixes, "
            "0 hits -- every key is read from the environment at call time"
        )

    # -- 16.13 [MVP] --------------------------------------------------------------
    @gate.criterion(
        "16.13", "every API route prefix is proxied by nginx and vite -- no SPA-fallback shadow"
    )
    def _() -> str:
        """The trap that has now bitten three times (D-057's `/models`, then `/auth`, then
        `/voice`): an API prefix with no proxy block falls through to `try_files ... /index.html`
        and answers **200 with HTML**. `fetch` then fails on `.json()`, and the UI reports
        something unrelated -- "transcription failed" while the provider was never reached.

        Derived from FastAPI's own route table rather than a hand-kept list, so a route added
        tomorrow is covered without anyone remembering to update this.
        """
        import re

        from src.api.main import app as fastapi_app

        nginx = (WEB / "nginx.conf").read_text(encoding="utf-8")
        vite = (WEB / "vite.config.ts").read_text(encoding="utf-8")

        # FastAPI mounts these itself. They are deliberately *not* proxied: the OpenAPI schema
        # and its two viewers do not belong on a public surface, and leaving them to the SPA
        # fallback is the intended outcome rather than the bug this criterion hunts. Excluded
        # by name so the carve-out is visible instead of the check being loosened.
        framework_routes = {"docs", "redoc", "openapi.json", "docs_oauth2_redirect"}

        # Everything the browser can call. `/mcp-apps` is reached only by the outer iframe but
        # is still browser-originated, so it counts.
        prefixes: set[str] = set()
        for route in fastapi_app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/") or path == "/":
                continue
            first = path.split("/")[1].split("{")[0]
            if first and first not in framework_routes:
                prefixes.add(first)

        missing_nginx = sorted(
            p for p in prefixes if not re.search(rf"location[^\n]*/{p}\b", nginx)
        )
        missing_vite = sorted(p for p in prefixes if f'"/{p}' not in vite)

        assert not missing_nginx, (
            "API prefixes with no nginx block -- these return index.html with a 200 in the "
            f"container: {missing_nginx}"
        )
        assert not missing_vite, f"API prefixes missing from vite.config.ts's proxy: {missing_vite}"
        return (
            f"{len(prefixes)} API prefixes derived from FastAPI's route table "
            f"({', '.join(sorted(prefixes))}); every one has an nginx block and a vite proxy entry"
        )

    # -- 16.12 [SCALE] ------------------------------------------------------------
    @gate.criterion("16.12", "[SCALE] barge-in and streaming TTS as the agent composes")
    def _() -> str:
        raise Pending(
            "barge-in (interrupting the agent mid-sentence) and streaming synthesis are "
            "PLAN-02 P16's own [SCALE] lines -- deferred per CONSTITUTION III.3"
        )

    return gate


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    return build_gate().run()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
