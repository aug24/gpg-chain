# GPG Chain

A distributed, append-only ledger for GPG public keys. Nodes gossip keys and trust signatures across a peer-to-peer network. Clients evaluate the web of trust locally — the server stores cryptographic material; it never decides what to trust.

Designed for key discovery: given your own key as a root of trust, you can find and evaluate keys you have never seen before by following the trust graph, including across independent ledger nodes.

## Quick links

- **[Getting started](docs/getting-started.md)** — install, run a node, run the tests
- **[How it works](docs/overview.md)** — concepts, architecture, design decisions
- **[Specifications](spec/)** — canonical definitions of the API, data model, signing payloads, trust algorithm, and P2P protocol

## At a glance

```
# Start a node
python implementations/python/node.py --allow-all-domains

# Run the test suite against it
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/

# Run multi-node integration tests (requires Docker)
./scripts/integration-test.sh
```

## Implementations

| Language | Location | Status |
|---|---|---|
| Python | `implementations/python/` | Reference — complete |
| Go | `implementations/go/` | In progress |

Both implementations conform to the same HTTP API (`spec/openapi.yaml`) and pass the same Gherkin test suite (`tests/features/`).
