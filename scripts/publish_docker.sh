#!/usr/bin/env bash
# Builds and pushes Cardinal's three published images to Docker Hub.
#
#   akbardebug/cardinal        one container, `docker run -p 8080:8080`, DEMO_MODE, no database
#   akbardebug/cardinal-api    the API + booking-mcp image the compose stack runs (two commands)
#   akbardebug/cardinal-web    the built SPA behind nginx, proxying to `api`
#
# Usage:
#   scripts/publish_docker.sh                      # build + push :0.1.0 and :latest, both arches
#   scripts/publish_docker.sh --version 0.2.0      # a different tag
#   scripts/publish_docker.sh --dry-run            # build only, never push (loads into the local
#                                                  #   daemon, single-arch -- buildx cannot load a
#                                                  #   multi-arch manifest into `docker images`)
#   scripts/publish_docker.sh --platforms linux/amd64
#
# CI does the same thing on a tag push: .github/workflows/docker-publish.yml.
set -euo pipefail

NAMESPACE="${CARDINAL_NAMESPACE:-akbardebug}"
VERSION="${CARDINAL_VERSION:-0.1.0}"
PLATFORMS="${CARDINAL_PLATFORMS:-linux/amd64,linux/arm64}"
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --version)   VERSION="$2"; shift 2 ;;
        --namespace) NAMESPACE="$2"; shift 2 ;;
        --platforms) PLATFORMS="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=1; shift ;;
        -h|--help)   sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/.."

REVISION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

# Is this machine logged in to Docker Hub? Deliberately not a grep for `auths` in config.json:
# with a credential helper configured (Docker Desktop always configures one) that object is
# empty, and the naive check reports "not logged in" on a machine that plainly is -- which is
# exactly how the first version of this script failed.
docker_hub_logged_in() {
    local cfg="${DOCKER_CONFIG:-$HOME/.docker}/config.json"
    [ -f "$cfg" ] || return 1

    # Credentials stored in the file itself (no helper configured).
    if grep -q '"https://index.docker.io/v1/"' "$cfg" && grep -q '"auth"' "$cfg"; then
        return 0
    fi

    # Credentials behind a helper -- ask the helper.
    local store
    store=$(sed -n 's/.*"credsStore"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$cfg" | head -1)
    if [ -n "$store" ] && command -v "docker-credential-$store" >/dev/null 2>&1; then
        "docker-credential-$store" list 2>/dev/null | grep -q 'index.docker.io' && return 0
    fi

    return 1
}

if [ "$DRY_RUN" -eq 1 ]; then
    # --load takes one platform: a multi-arch result is a manifest list, and the local image
    # store has nowhere to put one. Dry runs are about "does it build", so the host's arch is
    # the honest thing to check.
    PLATFORMS="$(echo "$PLATFORMS" | cut -d, -f1)"
    OUTPUT=(--load)
    echo "DRY RUN -- building $PLATFORMS locally, pushing nothing"
else
    OUTPUT=(--push)
    # Fail here rather than three builds later: an unauthenticated push 401s at the *end* of a
    # twenty-minute arm64 build. CARDINAL_SKIP_LOGIN_CHECK=1 overrides, so a detector that is
    # wrong on some setup can never be the thing that stops a release.
    if [ "${CARDINAL_SKIP_LOGIN_CHECK:-0}" != "1" ] && ! docker_hub_logged_in; then
        echo "not logged in to Docker Hub -- run: docker login -u $NAMESPACE" >&2
        echo "(if you are logged in and this is wrong: CARDINAL_SKIP_LOGIN_CHECK=1)" >&2
        exit 1
    fi
fi

# One builder, reused. The default `docker` driver cannot do multi-platform builds at all, so
# a `docker-container` builder is not optional here.
BUILDER=cardinal-publish
if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    echo "creating buildx builder '$BUILDER'"
    docker buildx create --name "$BUILDER" --driver docker-container --bootstrap >/dev/null
fi

build() {
    local image="$1" context="$2" dockerfile="$3"
    echo
    echo "=============================================================================="
    echo "  $NAMESPACE/$image:$VERSION  ($PLATFORMS)"
    echo "=============================================================================="
    docker buildx build \
        --builder "$BUILDER" \
        --platform "$PLATFORMS" \
        --file "$dockerfile" \
        --build-arg "VERSION=$VERSION" \
        --build-arg "REVISION=$REVISION" \
        --tag "$NAMESPACE/$image:$VERSION" \
        --tag "$NAMESPACE/$image:latest" \
        "${OUTPUT[@]}" \
        "$context"
}

build cardinal     .     Dockerfile.allinone
build cardinal-api .     Dockerfile
build cardinal-web ./web ./web/Dockerfile

echo
if [ "$DRY_RUN" -eq 1 ]; then
    echo "built (not pushed): $NAMESPACE/{cardinal,cardinal-api,cardinal-web}:$VERSION"
else
    echo "pushed $NAMESPACE/{cardinal,cardinal-api,cardinal-web} at :$VERSION and :latest"
    echo
    echo "  docker run -p 8080:8080 $NAMESPACE/cardinal"
fi
