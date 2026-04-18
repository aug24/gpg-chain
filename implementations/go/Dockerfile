## Stage 1 — build
FROM golang:1.22-alpine AS builder

WORKDIR /src

# Copy vendored deps first so this layer is cached independently of source changes
COPY vendor/ vendor/
COPY go.mod go.sum ./
COPY . .

# CGO_ENABLED=0: modernc.org/sqlite is pure Go — no C toolchain needed.
# -mod=vendor: build from the vendored tree; no network access required.
# -trimpath: remove local build paths from stack traces.
RUN CGO_ENABLED=0 GOOS=linux go build \
    -mod=vendor \
    -trimpath \
    -ldflags="-s -w" \
    -o /gpgchain-node \
    ./cmd/node/

## Stage 2 — runtime
# alpine: ~5 MB, has wget (needed for healthcheck), has CA certs for HTTPS peers.
FROM alpine:3.19

RUN apk add --no-cache ca-certificates wget

COPY --from=builder /gpgchain-node /gpgchain-node

EXPOSE 8080

ENTRYPOINT ["/gpgchain-node"]
CMD ["--addr", "0.0.0.0:8080", "--allow-all-domains", "--allow-private-peers"]
