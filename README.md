# GPG Chain

A distributed, append-only ledger for GPG public keys. Nodes gossip keys and trust signatures across a peer-to-peer network. Clients evaluate the web of trust locally — the server stores cryptographic material; it never decides what to trust.

Designed for key discovery: given your own key as a root of trust, you can find and evaluate keys you have never seen before by following the trust graph, including across independent ledger nodes.

## Quick links

- **[Getting started](docs/getting-started.md)** — install, run a node, run the tests
- **[How it works](docs/overview.md)** — concepts, architecture, design decisions
- **[CLI reference](docs/cli-reference.md)** — all client commands, flags, and exit codes
- **[User guide](docs/user-guide.md)** — practical walkthrough for participants
- **[Operator guide](docs/operator-guide.md)** — running a production node
- **[Trust guide](docs/trust-guide.md)** — choosing thresholds and understanding trust scoring
- **[Architecture](docs/architecture.md)** — internal design of both implementations
- **[For newcomers](docs/NEWBIE.md)** — why blockchain for key distribution, explained simply
- **[Specifications](spec/)** — canonical definitions of the API, data model, signing payloads, trust algorithm, and P2P protocol

## At a glance

```bash
# Build the Go binary
./scripts/build.sh

# Start a node (Go)
./implementations/go/cmd/node/node --allow-all-domains

# Or start the Python reference node
python implementations/python/node.py --allow-all-domains

# Add your key
gpgchain add --server http://localhost:8080 --key pubkey.asc --privkey privkey.asc

# Run the test suite
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/

# Run multi-node integration tests (requires Docker)
./scripts/integration-test.sh
```

## Implementations

| Language | Location | Status |
|---|---|---|
| Python | `implementations/python/` | Reference — complete |
| Go | `implementations/go/` | Complete |

Both implementations conform to the same HTTP API (`spec/openapi.yaml`) and pass the same Gherkin test suite (`tests/features/`). The Go implementation includes a full CLI client (`gpgchain`) with nine commands.
