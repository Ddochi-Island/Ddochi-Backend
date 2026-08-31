# syntax=docker/dockerfile:1.7
#
# Multi-stage build for data_router. Final image is distroless/static
# (~2 MB) with CA certs for outbound TLS to ADB and OCI Object Storage.
# The binary is statically linked (CGO_ENABLED=0), so no glibc/musl in
# the runtime layer. Runs as non-root.
#
# Build args:
#   GO_VERSION    — Go toolchain version (default 1.22)
#   TARGETOS,TARGETARCH — set automatically by buildx; default to host
#
# What's NOT in the image (intentionally):
#   - .env / wallet_v2 / OCI keys — mount via Cloud Run secret volumes
#     or pass via env vars at runtime. Image stays publishable to a
#     private Artifact Registry without holding any secret material.

ARG GO_VERSION=1.22

FROM golang:${GO_VERSION}-bookworm AS builder

WORKDIR /src

# Cache module downloads in a separate layer.
COPY go.mod go.sum ./
RUN go mod download

COPY . .

ARG TARGETOS=linux
ARG TARGETARCH=amd64

# -trimpath strips local paths from the binary; -ldflags shrinks size
# and embeds a build stamp. CGO disabled so the result is fully static.
RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build \
        -trimpath \
        -ldflags="-s -w -X main.buildVersion=$(date -u +%Y%m%dT%H%M%SZ)" \
        -o /out/data_router \
        ./cmd/data_router

# ────────────────── runtime: code only (default target) ──────────────────
# Use this for local `docker build .` where the wallet isn't available.
# The image won't connect to ADB at boot — useful for smoke tests.
FROM gcr.io/distroless/static-debian12:nonroot AS runtime
ENV PORT=8080
COPY --from=builder /out/data_router /usr/local/bin/data_router
USER nonroot:nonroot
ENTRYPOINT ["/usr/local/bin/data_router"]

# ────────────────── runtime: code + wallet (prod) ──────────────────
# Selected by deploy.sh via `--target=runtime-with-wallet`. Expects the
# build context to contain a `wallet/` directory (cwallet.sso, etc.).
# deploy.sh stages ../../wallet_v2 into a temp dir before building so
# the production wallet doesn't sit inside the source tree.
FROM runtime AS runtime-with-wallet
COPY --chown=nonroot:nonroot wallet/ /app/wallet/
