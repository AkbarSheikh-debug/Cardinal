# ---- builder: real `vite build`, not the dev server (PHASE-11 SS3) --------------------------
FROM node:22-slim AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- runtime: static files behind nginx, non-root out of the box ----------------------------
# `nginxinc/nginx-unprivileged` runs as a non-root user and listens above port 1024 by
# default -- the supported way to get a non-root nginx image without hand-patching the
# official one's pidfile/listen-port ownership.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8080/ || exit 1
