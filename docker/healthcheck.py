"""HEALTHCHECK for the all-in-one image -- all three processes, not just the front one.

`Dockerfile`'s (compose) probe hits `/health` on the API directly because that container runs
one process. Here a bare `/health` through nginx would prove nginx and the API and say nothing
about booking-mcp, so a container whose checkout path is dead would still report healthy --
which is the one thing a healthcheck is for.

No `curl`/`wget` in `python:3.12-slim`, hence stdlib. Exit 0 healthy, 1 not (Docker's contract).
"""

from __future__ import annotations

import socket
import sys
import urllib.request

TIMEOUT = 3.0


def main() -> int:
    try:
        # nginx (:8080) proxying /health to the API (:8000) -- one request, both processes.
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=TIMEOUT) as response:
            if response.status != 200:
                print(f"api via nginx: HTTP {response.status}", file=sys.stderr)
                return 1
    # Bare `Exception` on purpose: any failure at all -- connection refused, timeout, a garbled
    # response -- means unhealthy, and a healthcheck that raised instead of exiting 1 would look
    # to Docker like a broken probe rather than a sick container.
    except Exception as exc:
        print(f"api via nginx: {exc}", file=sys.stderr)
        return 1

    try:
        # booking-mcp mounts /mcp (a JSON-RPC POST), so there is no cheap GET to make. A TCP
        # connect is enough to know its uvicorn is accepting -- same reasoning, and the same
        # probe, as the `booking` service's healthcheck in docker-compose.yml.
        socket.create_connection(("127.0.0.1", 8100), timeout=TIMEOUT).close()
    except OSError as exc:
        print(f"booking-mcp: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
