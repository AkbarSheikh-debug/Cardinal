# Shared by both Python services in docker-compose.yml -- `api` (uvicorn) and `booking`
# (booking-mcp's standalone HTTP transport, PHASE-11 SS3's "separate service, own hostname").
# One image, two `command:` overrides in compose -- they're the same dependency set and the
# same non-root runtime, so a second near-identical Dockerfile would only be something to keep
# in sync by hand.

# ---- builder: resolve dependencies and build the `cardinal` wheel in a throwaway layer ------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Dependencies first, so editing src/ doesn't invalidate this layer.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

# ---- runtime: just the venv plus the non-package entry points, non-root, healthchecked ------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system cardinal \
    && useradd --system --create-home --gid cardinal cardinal

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# `alembic upgrade head` and `python -m scripts.seed_marketplace` need these at runtime;
# `src/` itself is not copied here -- it's already installed into the venv above as the
# `cardinal` package (pyproject.toml's `[tool.setuptools.packages.find]` covers `src*`).
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
# `src/agent/prompts.py`'s `load_prompt` (CONSTITUTION III.6) falls back to reading this
# directory relative to cwd when it isn't installed as package data -- not copied here, the
# live orchestrator's every prompt file fails to load the first time anything reaches it.
COPY prompts/ ./prompts/

RUN chown -R cardinal:cardinal /app
USER cardinal

EXPOSE 8000

# `booking`'s compose entry overrides this with a TCP check on :8100 (no HTTP health route
# exists on that transport -- it only mounts /mcp) -- this default is `api`'s.
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
