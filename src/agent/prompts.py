"""Loads prompt text from `prompts/` (CONSTITUTION III.6, gate 3.7).

Nothing in `src/` should carry a prompt string over 200 characters -- prompts get reviewed,
diffed and versioned like code, in their own files, not buried in a Python literal where a
regression is invisible in `git log`. This is the one place `src/agent` is allowed to know
prompt *content* exists; everywhere else just calls `load_prompt(name)`.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
if not PROMPTS_DIR.is_dir():
    # Docker's runtime image `pip install`s `src` into site-packages rather than running from
    # a source checkout, so `parents[2]` no longer lands on the repo root there -- it lands
    # inside site-packages instead. `WORKDIR` is `/app` and `prompts/` is copied there alongside
    # `alembic.ini`/`migrations/`/`scripts/` (same layout, same reasoning), so cwd is the
    # fallback, not the primary: a source checkout invoked from some other cwd still gets
    # `load_prompt`'s loud `FileNotFoundError` instead of silently reading the wrong directory.
    PROMPTS_DIR = Path.cwd() / "prompts"


@cache
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no prompt file at {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path} is empty")
    return text
