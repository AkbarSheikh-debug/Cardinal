# cardinal-api — Cardinal's backend and booking MCP server

The FastAPI backend for [Cardinal](https://github.com/AkbarSheikh-debug/Cardinal), a
multistep car-buying agent. **This image is one half of a stack, not a standalone app** — if
you want to *look at* Cardinal, use [`akbardebug/cardinal`](https://hub.docker.com/r/akbardebug/cardinal)
instead:

```bash
docker run -p 8080:8080 akbardebug/cardinal
```

## What this image is for

It runs two different services depending on the `command` it is given, because they share a
dependency set and a runtime and a second near-identical image would only be something to keep
in sync by hand:

```yaml
# the API
command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# the booking MCP server — its own hostname, no published port
command: ["python", "-m", "src.mcp.booking.http"]
```

Use it through the project's compose file, which wires both plus Postgres and the frontend:

```bash
curl -O https://raw.githubusercontent.com/AkbarSheikh-debug/Cardinal/main/docker-compose.hub.yml
docker compose -f docker-compose.hub.yml up
```

Then open http://localhost:5173.

## Configuration

| Variable | Meaning |
|---|---|
| `DEMO_MODE` | `true` runs the scripted flow with no model calls and no database |
| `ANTHROPIC_API_KEY` | Required when `DEMO_MODE` is not `true` |
| `CARDINAL_DATABASE_URL` | `postgresql+psycopg://…`; falls back to an in-memory catalogue when unset |
| `CARDINAL_BOOKING_MCP_URL` | Where the API reaches the booking MCP server. Note the trailing slash: `http://booking:8100/mcp/` |
| `BOOKING_MCP_HTTP_HOST` / `_PORT` | Bind address for the booking MCP command |

`GET /health` reports status, backend (`memory` or `postgres`), demo mode and catalogue size.

Migrations and seeding are in the image: `alembic upgrade head` and
`python -m scripts.seed_marketplace --if-empty`.

Non-root (`cardinal`), `linux/amd64` (a `v*` tag also publishes `linux/arm64`). MIT licensed.
