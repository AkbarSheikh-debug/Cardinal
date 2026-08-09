# Cardinal — a car-buying agent you can argue with

```bash
docker run -p 8080:8080 akbardebug/cardinal
```

Open **http://localhost:8080**. No API key, no database, no configuration — the image boots
into a scripted demo mode that walks the complete flow.

Cardinal interviews a buyer about budget, use and timing, researches rental and dealership
marketplaces on their behalf, and returns ranked recommendations **it can defend** — every
score opens into the weights that produced it. Booking and payment happen inside the
conversation.

Source: **https://github.com/AkbarSheikh-debug/Cardinal**

---

## What's in the container

One container, three processes: the built React frontend behind nginx (`:8080`, the only
published port), the FastAPI backend (`:8000`, loopback), and the booking MCP server
(`:8100`, loopback). Runs as a non-root user. If any process dies the container exits rather
than serving a healthy-looking 502.

| | |
|---|---|
| **Port** | `8080` — nginx, SPA + reverse proxy |
| **User** | non-root (`cardinal`) |
| **Healthcheck** | built in; checks the API *and* the MCP server, not just the front door |
| **Database** | none required — the 240-listing catalogue is generated in memory |
| **Size** | ~810MB (285MB of it is the Claude Agent SDK's bundled CLI, needed for live mode) |
| **Platforms** | `linux/amd64` (see Tags below for arm64) |

## Try it

| Go to | To see |
|---|---|
| `/` | The showroom |
| `/chat` | The agent — interview → research → ranked results with reasoning |
| `/login` | Sign in. Demo accounts use fixed OTP codes, returned by the API itself |
| `/cart` | Add a car from a result card, then checkout with payee disclosure |
| `/seller` | The dealer console — leads, intent tiers, and the signals behind each |

Sign-in is a mock: `POST /auth/request-otp` returns the accepted codes in its own response
body, because an authentication system that only *looks* real is worse than one that says so.

## The rule that does not bend

**No booking is ever confirmed without a human click.** The confirming tool is not in the set
the model can see, and the gesture that unlocks it has to come from a real pointer event. That
is enforced in code and covered by a test, not asked for in a prompt.

## Running the live agent

```bash
docker run -p 8080:8080 -e DEMO_MODE=false -e ANTHROPIC_API_KEY=sk-ant-... akbardebug/cardinal
```

Same image. Demo mode is a scripted replay of the same pipeline; turning it off puts a real
model behind the same UI.

Optional: `CARDINAL_DATABASE_URL` (a `postgresql+psycopg://…` URL) makes the container migrate
and seed a real Postgres on startup instead of using the in-memory catalogue.

## The full stack instead

This image is one container for convenience. The real deployment shape is four services —
Postgres, the API, the booking MCP server on its own hostname, and nginx:

```bash
curl -O https://raw.githubusercontent.com/AkbarSheikh-debug/Cardinal/main/docker-compose.hub.yml
docker compose -f docker-compose.hub.yml up
```

Then open http://localhost:5173. That pulls
[`cardinal-api`](https://hub.docker.com/r/akbardebug/cardinal-api) and
[`cardinal-web`](https://hub.docker.com/r/akbardebug/cardinal-web).

## Tags

`latest` and `0.1.0`, built for `linux/amd64`.

**On Apple silicon** this runs under emulation — it works, and it is slower to start. A native
`linux/arm64` image is built and published by the release workflow on a `v*` tag
(`.github/workflows/docker-publish.yml`); once one has run, both architectures resolve from the
same tag automatically.

---

Built for the Amulate Summer Hackathon 2026. MIT licensed. The dealers, listings and prices are
generated, not scraped — the catalogue is synthetic on purpose and no real dealership's data is
in it.
