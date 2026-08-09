PYTHON ?= python
PHASES := 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16

# Docker Hub coordinates for the published images (scripts/publish_docker.sh, D-093).
NAMESPACE ?= akbardebug
VERSION ?= 0.1.0

.PHONY: help dev test lint typecheck verify gate gates seed migrate up down clean \
	image run docker-build docker-push hub-up hub-down

help:  ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-12s %s\n", $$1, $$2}'

dev:  ## api on :8000
	$(PYTHON) -m uvicorn src.api.main:app --reload --port 8000

test:  ## unit + contract + integration
	$(PYTHON) -m pytest tests -q

lint:  ## ruff
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests scripts

format:  ## ruff format, in place
	$(PYTHON) -m ruff format src tests scripts
	$(PYTHON) -m ruff check --fix src tests scripts

# agent is held to the domain's strict bar via pyproject's per-module override, not the
# --strict CLI flag -- the CLI flag would sweep transitively-imported (not-yet-strict)
# adapters code into strict mode too, since agent legitimately imports adapters.
typecheck:  ## mypy, strict on the domain
	$(PYTHON) -m mypy --strict src/domain
	$(PYTHON) -m mypy src/agent src/adapters src/api src/mcp

# CONSTITUTION III.1: a phase is done when its gate prints green -- run, not read.
gate:  ## make gate PHASE=1
	$(PYTHON) -m scripts.gate_phase$(PHASE)

gates:  ## every gate, 0..16, stopping at the first red one
	@for p in $(PHASES); do $(PYTHON) -m scripts.gate_phase$$p || exit 1; done

verify: lint typecheck test gates  ## everything, chained

seed:  ## seed the catalogue into Postgres
	$(PYTHON) -m scripts.seed_marketplace

migrate:  ## alembic upgrade head
	$(PYTHON) -m alembic upgrade head

up:  ## docker compose up --build
	docker compose up --build -d

down:  ## stop the stack, keep the volume
	docker compose down

clean:  ## stop the stack and drop the data volume
	docker compose down -v

# ---- published images (Docker Hub) ----------------------------------------------------------

image:  ## build the one-container image locally
	docker build -f Dockerfile.allinone \
		--build-arg VERSION=$(VERSION) \
		--build-arg REVISION=$$(git rev-parse --short HEAD) \
		-t $(NAMESPACE)/cardinal:$(VERSION) -t $(NAMESPACE)/cardinal:latest .

run: image  ## build it and open the whole app on :8080, no keys, no database
	docker run --rm -p 8080:8080 $(NAMESPACE)/cardinal:$(VERSION)

docker-build:  ## build all three published images, push nothing
	bash scripts/publish_docker.sh --dry-run --version $(VERSION) --namespace $(NAMESPACE)

docker-push:  ## build all three for amd64+arm64 and push to Docker Hub (needs docker login)
	bash scripts/publish_docker.sh --version $(VERSION) --namespace $(NAMESPACE)

hub-up:  ## run the full stack from published images, no build
	docker compose -f docker-compose.hub.yml up

hub-down:  ## stop it
	docker compose -f docker-compose.hub.yml down
