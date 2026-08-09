# cardinal-web — Cardinal's frontend

The built React frontend for [Cardinal](https://github.com/AkbarSheikh-debug/Cardinal),
served by nginx, which also reverse-proxies every backend route to a host named `api`.

**This image is one half of a stack, not a standalone app.** On its own it serves the SPA and
502s on every API call, because there is no `api` to proxy to. If you want to *look at*
Cardinal, use [`akbardebug/cardinal`](https://hub.docker.com/r/akbardebug/cardinal):

```bash
docker run -p 8080:8080 akbardebug/cardinal
```

## Using it properly

```bash
curl -O https://raw.githubusercontent.com/AkbarSheikh-debug/Cardinal/main/docker-compose.hub.yml
docker compose -f docker-compose.hub.yml up
```

Then open http://localhost:5173. That brings up this image alongside
[`cardinal-api`](https://hub.docker.com/r/akbardebug/cardinal-api) and Postgres, with Docker's
internal DNS resolving `api` for the proxy blocks.

## Details

- Listens on **8080**, non-root (`nginxinc/nginx-unprivileged`).
- Server-sent-event routes (`/sessions/{id}/events`, `/seller/events`) are proxied unbuffered —
  buffering them turns a live stream into a page that looks frozen.
- Agent turns get a 300s read timeout; nginx's 60s default cut real turns off as a 504.
- Everything else falls through to `index.html` for client-side routing.

`linux/amd64` (a `v*` tag also publishes `linux/arm64`). MIT licensed.
