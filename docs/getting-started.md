# Getting Started

This guide walks a new developer through cloning the repository, setting up the Python reference implementation, running the test suite, and spinning up a local multi-node cluster.

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | 3.11 or 3.12 recommended; see note below for 3.13+ |
| pip | any recent | used to install Python deps |
| Docker + Compose | Docker 24 / Compose v2 | only needed for multi-node integration tests |

> **Python 3.13+ compatibility note** — `pgpy 0.6.0` imports the `imghdr` standard-library module which was removed in Python 3.13. On Python 3.13 or 3.14 you need to patch the installed package once after `pip install`:
> ```
> python scripts/patch_pgpy.py
> ```
> (or apply the patch manually: wrap `import imghdr` in a `try/except ImportError` in `site-packages/pgpy/constants.py`).
> Using Python 3.11 or 3.12 avoids this entirely.

---

## 1 — Clone and install

```bash
git clone <repo-url> gpg-chain
cd gpg-chain
```

Install the Python implementation in editable mode together with all dependencies:

```bash
pip install -e implementations/python/
```

Install test dependencies:

```bash
pip install -r tests/requirements.txt
```

Verify the node starts:

```bash
python implementations/python/node.py --help
```

---

## 2 — Run a single node

```bash
python implementations/python/node.py \
    --addr 0.0.0.0:8080 \
    --store-dir /tmp/gpgchain-dev \
    --allow-all-domains
```

The node is now listening at `http://localhost:8080`.
Smoke-test it:

```bash
curl http://localhost:8080/peers
# → []

curl http://localhost:8080/.well-known/gpgchain.json
# → {"node_url": "", "domains": [], "peers": []}
```

---

## 3 — Run the test suite (single-node)

The Gherkin test suite lives in `tests/features/`.  It runs with `behave` against a live HTTP server.

With your node running on port 8080 in another terminal:

```bash
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/
```

Expected output (numbers may vary as new scenarios are added):

```
11 features passed, 0 failed, 3 skipped
56 scenarios passed, 0 failed, 23 skipped
```

The skipped scenarios require two or more nodes (gossip, sync, cross-validation) and are covered by the Docker Compose integration tests in section 5.

### Running a specific feature

```bash
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/features/adding-keys.feature
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/features/signing-keys.feature
```

### Verbose output

```bash
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/ --no-capture
```

---

## 4 — Project layout

```
gpg-chain/
  spec/                   Canonical specifications — read these first
    openapi.yaml          HTTP API definition (source of truth for all endpoints)
    data-model.md         Block + SigEntry structure, hash computation
    payloads.md           Binary signing payload formats
    trust.md              Trust graph algorithm
    p2p.md                Gossip, sync, peer exchange protocol

  implementations/
    python/               Reference implementation (clarity over performance)
      gpgchain/
        api/              FastAPI routes and application factory
        chain/            Block/SigEntry models and hash computation
        gpg/              Key parsing, signature verification, payload construction
        store/            DirStore (directory tree + LRU cache)
        p2p/              Gossip, sync, peer management
        trust/            Trust graph evaluation
      node.py             Node entry point (run with `python node.py`)
      client.py           CLI client entry point
      requirements.txt    All runtime + test dependencies
      pyproject.toml      Package metadata

    go/                   Production implementation (not yet complete)

  tests/
    features/             Gherkin .feature files — language-agnostic
    steps/                behave step definitions
    support/
      client.py           Thin HTTP wrapper used by step definitions
      gpg_helper.py       Pure-Python key generation and signing (pgpy)
    requirements.txt      behave + requests + pgpy

  scripts/
    integration-test.sh   Build cluster, run full suite, tear down
    cluster.sh            Manual cluster management (start/stop/status)
    build.sh              Build all implementations
    clean.sh              Stop nodes, remove data directories

  docker-compose.yml      Three-node cluster for integration testing
  docs/                   This directory
  spec/                   Specifications
```

---

## 5 — Multi-node integration tests (Docker Compose)

These tests exercise P2P gossip, sync-on-connect, and cross-validation.  They require Docker.

### One-shot (build, test, tear down)

```bash
./scripts/integration-test.sh
```

The script:
1. Builds the Python Docker image
2. Starts three nodes (node-a :8080, node-b :8081, node-c :8082)
3. Waits for all health checks to pass
4. Runs `behave` with all three server URLs in `GPGCHAIN_TEST_SERVER`
5. Tears down the cluster and removes volumes

### Iterating without rebuilding

```bash
./scripts/integration-test.sh --no-build
```

### Leave the cluster running after tests

```bash
./scripts/integration-test.sh --keep-up

# Then run behave yourself, or poke the nodes manually
GPGCHAIN_TEST_SERVER=http://localhost:8080,http://localhost:8081,http://localhost:8082 \
  behave tests/

# Tear down when done
docker compose down -v
```

### Starting the cluster manually

```bash
docker compose up -d          # start all three nodes
docker compose ps             # check status
docker compose logs -f node-a # follow logs for node-a
docker compose down -v        # stop and remove volumes
```

### How multi-node scenarios work

When `GPGCHAIN_TEST_SERVER` contains multiple URLs:

- `context.servers[0]` → node-a
- `context.servers[1]` → node-b
- `context.servers[2]` → node-c

Gossip scenarios peer the nodes via `POST /peers` in the `Given` step, submit a block or signature to one node, then poll the other node until it appears (up to 15 seconds).  Sync scenarios use the same polling pattern after triggering sync via peer registration.

The nodes accept private Docker bridge IPs because they are started with `GPGCHAIN_ALLOW_PRIVATE_PEERS=true`.  This flag is only for controlled internal deployments — never use it on a public-facing node.

---

## 6 — Key node flags

| Flag | Environment variable | Default | Purpose |
|---|---|---|---|
| `--addr` | — | `0.0.0.0:8080` | Listen address |
| `--store-dir` | `GPGCHAIN_STORE_DIR` | `./data` | Block storage directory |
| `--allow-all-domains` | `GPGCHAIN_ALLOW_ALL=true` | off | Accept keys from any email domain |
| `--domains` | `GPGCHAIN_DOMAINS` | (empty) | Comma-separated allowed email domains |
| `--node-url` | `GPGCHAIN_NODE_URL` | (empty) | This node's public URL (returned by `/.well-known/`) |
| `--peers` | — | (empty) | Comma-separated bootstrap peer URLs |
| `--allow-private-peers` | `GPGCHAIN_ALLOW_PRIVATE_PEERS=true` | off | Skip private IP rejection (containers only) |
| `--cache-size` | — | `128` | LRU block cache capacity |

---

## 7 — Exploring the API

With a node running, the OpenAPI docs are available at:

```
http://localhost:8080/docs
```

Or browse `spec/openapi.yaml` directly for the canonical definition.

Quick examples:

```bash
# Add a key (you need a real self-signature — use the CLI client)
python implementations/python/client.py add \
    --server http://localhost:8080 \
    --key pubkey.asc \
    --keyid MYFINGERPRINT

# List all blocks
curl http://localhost:8080/blocks

# Search by email
curl "http://localhost:8080/search?q=alice@example.com"

# Peer with another node
curl -X POST http://localhost:8080/peers \
     -H 'Content-Type: application/json' \
     -d '{"addr": "http://other-node:8080"}'

# Fetch hash map (for sync/validation)
curl http://localhost:8080/p2p/hashes
```

---

## 8 — Understanding the test architecture

The test suite is entirely black-box HTTP.  Step definitions in `tests/steps/` use `APIClient` (a thin `requests` wrapper) and `GPGHelper` (a pure-Python key generator and signer built on `pgpy`).

- **No `gpg` subprocess** — all cryptographic operations in tests use `pgpy` directly.  No `gpg-agent` is started.
- **No mocking inside tests** — tests talk to a real running server.  The only mocking occurs in the in-process P2P unit tests (`p2p_steps.py`) which patch `socket.getaddrinfo` and `httpx.get` to bypass the private-IP and reachability checks.
- **Scenario isolation** — `before_scenario` in `environment.py` resets `context.client`, `context.keys`, and `context.submitted_blocks`.  Each scenario generates fresh ephemeral keys.
- **Multi-node scenarios** — skip gracefully when only one server URL is provided; activate fully when two or more URLs are given.

---

## 9 — Adding a new implementation

See `docs/new-implementation.md` for a full guide.  The short version:

1. Implement the HTTP API defined in `spec/openapi.yaml`.
2. Point the test suite at your server: `GPGCHAIN_TEST_SERVER=http://localhost:9000 behave tests/`.
3. All scenarios in `tests/features/` must pass.  The feature files are the compliance specification.
