# GPG Chain — Python Reference Implementation

This is the **reference implementation** of GPG Chain. It is written for clarity and direct correspondence with the spec, not for performance. Every spec behaviour is implemented as directly as possible with no optimisations that obscure intent.

---

## What it does

A GPG Chain node stores GPG public keys and trust signatures in a content-addressed ledger, gossips new entries to peers, and exposes a REST API for clients and other nodes. Trust evaluation is always client-side — the node is a pure store and retrieval layer.

---

## Quick start

```bash
# Install (from the repo root)
pip install -e implementations/python/

# Run a node that accepts keys from any domain
python implementations/python/node.py --allow-all-domains

# Smoke test
curl http://localhost:8080/peers           # → []
curl http://localhost:8080/.well-known/gpgchain.json
```

Run the test suite against it (in a second terminal):

```bash
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/
# Expected: 11 features passed, 0 failed, 3 skipped
#           56 scenarios passed, 0 failed, 23 skipped
```

---

## Layout

```
implementations/python/
  gpgchain/
    api/
      app.py        Application factory — creates FastAPI app and mounts state
      routes.py     All HTTP route handlers (public + peer + P2P endpoints)
    chain/
      models.py     Block and SigEntry dataclasses
      hashing.py    compute_block_hash, compute_sig_entry_hash
    gpg/
      keys.py       parse_armored_key, check_key_strength, extract_email_domains
      payloads.py   submit_payload, trust_payload, revoke_payload
      verify.py     verify_detached_sig
    store/
      dir_store.py  DirStore — directory tree of JSON files with LRU cache
      memory.py     MemoryStore — in-memory store used by tests
    p2p/
      gossip.py     Gossip — bounded fanout, seen-set deduplication
      sync.py       Sync — sync_with_peer, cross_validate
    trust/
      graph.py      Trust graph: build, score, is_trusted, trusted_set
  node.py           Entry point: parse flags, wire components, start uvicorn
  client.py         CLI client: add, sign, revoke, list, check, show, search, verify
  pyproject.toml    Package metadata and dependencies
  requirements.txt  Flat dependency list (same as pyproject.toml deps)
```

---

## Key packages

### `chain/`
Defines `Block` and `SigEntry` dataclasses and the two hash functions.

**Block hash** = SHA-256 of `fingerprint \x00 armored_key \x00 self_sig` (uppercase hex).

**SigEntry hash** = SHA-256 of `prev_hash \x00 signer_fingerprint \x00 sig \x00 timestamp` (uppercase hex).

### `gpg/`
All OpenPGP operations using `pgpy` — no `gpg` subprocess, no gpg-agent.

- `parse_armored_key` — returns `(fingerprint, [uid, ...])` from ASCII-armored key
- `check_key_strength` — rejects RSA < 2048 bit and DSA-1024
- `submit_payload` / `trust_payload` / `revoke_payload` — construct typed binary signing payloads
- `verify_detached_sig` — verifies a base64-encoded detached binary OpenPGP signature

### `store/`
Two implementations of a simple key-value store keyed by fingerprint.

**DirStore** persists each block and SigEntry as a separate JSON file:
```
<store-dir>/AB/CD/ABCD...1234.block.json
<store-dir>/AB/CD/ABCD...1234.sig.<sighash>.json
<store-dir>/AB/CD/ABCD...1234.revoke.json
```
Writes are atomic (write to `.tmp`, then rename). An LRU cache (default 128 entries) sits in front.

**MemoryStore** — used by multi-node P2P tests where each scenario needs a fresh store.

### `api/routes.py`
All HTTP handlers. There are three groups:

| Prefix | Purpose |
|---|---|
| `/block`, `/blocks`, `/search` | Client-facing key management |
| `/peers`, `/.well-known/` | Peer discovery |
| `/p2p/*` | Inter-node gossip and sync |

Each handler validates input, calls the store, fires a gossip background task, and returns JSON. See `spec/openapi.yaml` for the full contract.

### `p2p/`
- **Gossip**: on receiving a new event, forward to K=3 randomly selected peers (excluding origin). A seen-set (TTL 1 hour) prevents forwarding the same event twice.
- **Sync**: on connecting to a peer, exchange `{fingerprint: sig_chain_head}` maps; fetch missing blocks and sig entries; push blocks the peer is missing. All received data is cryptographically verified before storage.

### `trust/graph.py`
Client-side trust evaluation. Builds an adjacency map from a list of blocks (revoked keys are dead ends), then counts distinct non-cyclic paths from the root key to a target using BFS. Cycle detection prevents infinite loops.

---

## Node flags

| Flag | Env var | Default | Purpose |
|---|---|---|---|
| `--addr` | — | `0.0.0.0:8080` | Listen address |
| `--store-dir` | `GPGCHAIN_STORE_DIR` | `./data` | Block storage directory |
| `--allow-all-domains` | `GPGCHAIN_ALLOW_ALL=true` | off | Accept keys from any domain |
| `--domains` | `GPGCHAIN_DOMAINS` | (empty) | Comma-separated allowed domains |
| `--node-url` | `GPGCHAIN_NODE_URL` | (empty) | This node's public URL |
| `--peers` | — | (empty) | Bootstrap peer URLs |
| `--allow-private-peers` | `GPGCHAIN_ALLOW_PRIVATE_PEERS=true` | off | Skip private IP rejection (containers only) |
| `--cache-size` | — | `128` | LRU block cache size |

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | HTTP framework |
| `uvicorn[standard]` | ASGI server |
| `pydantic` | Request validation |
| `httpx` | Async HTTP client (gossip, peer reachability) |
| `pgpy` | OpenPGP operations |
| `cachetools` | LRU cache |
| `click` | CLI client argument parsing |

---

## Further reading

- `spec/openapi.yaml` — canonical HTTP API
- `spec/data-model.md` — block/SigEntry fields and hash computation
- `spec/payloads.md` — binary signing payload formats
- `spec/trust.md` — BFS trust algorithm
- `spec/p2p.md` — gossip, sync, cross-validation
