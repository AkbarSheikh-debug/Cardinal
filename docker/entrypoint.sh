#!/usr/bin/env bash
# Supervises the three processes the all-in-one image (`Dockerfile.allinone`) runs:
#
#   booking-mcp   127.0.0.1:8100   loopback only, exactly as in compose (CONSTITUTION II.5)
#   api           127.0.0.1:8000   loopback only -- nginx is the only thing that reaches it
#   nginx         0.0.0.0:8080     the one published port; SPA + reverse proxy
#
# This is deliberately not supervisord or s6: the contract wanted here is "if any one of the
# three dies, the container dies", which is the opposite of what a supervisor is for. A
# supervisor restarting a crashed API behind a healthy-looking nginx is precisely the failure
# that leaves someone staring at a 502 with a green container.
#
# The four-service compose stack is still the real deployment shape (PHASE-11 SS3): separate
# images, separate hostnames, separate lifecycles. This image exists so that trying Cardinal
# costs one `docker run` and no clone -- see DECISIONS.md D-092.
set -uo pipefail

NGINX_TMP=/tmp/nginx
mkdir -p "$NGINX_TMP"/{client_body,proxy,fastcgi,uwsgi,scgi}

# Postgres is optional here and unset by default: `build_store` and its five siblings in
# src/api/main.py fall back to the generated in-memory catalogue, which is what makes
# CONSTITUTION III.7 ("the whole flow runs with the environment unset") true for this image.
# Point CARDINAL_DATABASE_URL at a real database and it migrates and seeds on the way up
# instead -- the same two commands the `api` compose service runs.
if [ -n "${CARDINAL_DATABASE_URL:-}" ]; then
    echo "cardinal: CARDINAL_DATABASE_URL is set -- migrating and seeding"
    alembic upgrade head || exit 1
    python -m scripts.seed_marketplace --if-empty || exit 1
fi

pids=()

terminate() {
    trap - TERM INT EXIT
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Give each child a moment to close its listener before the container goes away, so a
    # `docker stop` reads as a clean shutdown in the logs rather than a SIGKILL.
    for _ in $(seq 1 50); do
        running=0
        for pid in "${pids[@]}"; do
            kill -0 "$pid" 2>/dev/null && running=1
        done
        [ "$running" -eq 0 ] && break
        sleep 0.1
    done
}
trap terminate TERM INT EXIT

echo "cardinal: starting booking-mcp on 127.0.0.1:8100"
python -m src.mcp.booking.http &
pids+=($!)

echo "cardinal: starting api on 127.0.0.1:8000"
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 &
pids+=($!)

echo "cardinal: starting nginx on 0.0.0.0:8080"
nginx -c /etc/nginx/nginx.conf &
pids+=($!)

echo "cardinal: ready -- open http://localhost:8080"

# The first process to exit takes the container with it, carrying its exit code out so
# `docker inspect` reports why rather than a bare 0.
wait -n
code=$?
echo "cardinal: a supervised process exited ($code) -- shutting the container down"
exit "$code"
