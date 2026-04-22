# Architecture

This document describes the internal design of both GPG Chain implementations: the Python reference and the Go production implementation. Read `docs/overview.md` first for the conceptual background.

---

## Common structure

Both implementations expose the same HTTP API (defined in `spec/openapi.yaml`) and share the same internal decomposition:

```
HTTP layer      — request routing, validation, JSON serialisation
Chain layer     — Block and SigEntry models, hash computation
GPG layer       — key parsing, signature verification, payload construction
Store layer     — persistent storage of blocks, SigEntries, revocations
P2P layer       — gossip, sync-on-connect, peer management, cross-validation
Trust layer     — BFS scoring, disjoint scoring, trusted-set computation
```

The store is the single source of truth. No layer other than the store writes to disk. All other layers are stateless with respect to persistence.

---

## Python implementation

**Location:** `implementations/python/`

### HTTP layer — FastAPI

`gpgchain/api/routes.py` registers all routes against a FastAPI `app` instance created by `gpgchain/api/app.py`. Application state (peer list, domain config, store reference) is stored on `app.state`. Pydantic models provide automatic request validation and OpenAPI schema generation.

The `/docs` endpoint (Swagger UI) is provided automatically by FastAPI.

### Chain layer

`gpgchain/chain/` defines:

- `Block` — Pydantic model mirroring the spec data model
- `SigEntry` — Pydantic model for a single trust signature
- `compute_block_hash(fingerprint, armored_key, self_sig)` — SHA-256 over the three fields
- `compute_sig_entry_hash(prev_hash, signer_fp, sig, timestamp)` — SHA-256 over the four fields

### GPG layer

`gpgchain/gpg/` uses `pgpy` directly (no `gpg` subprocess, no `gpg-agent`):

- `parse_key(armored)` — returns fingerprint and UIDs
- `verify_self_sig(armored_key, self_sig_b64, fingerprint, timestamp)` — verifies SUBMIT payload signature
- `verify_trust_sig(armored_key, sig_b64, block_hash, signer_fp, timestamp)` — verifies TRUST payload signature
- `verify_revocation_sig(armored_key, sig_b64, fingerprint, block_hash)` — verifies REVOKE payload signature
- `sign_payload(armored_privkey, payload_bytes)` — signs arbitrary payload, returns base64

### Store layer — directory tree

`gpgchain/store/dir_store.py` implements a content-addressed directory tree:

```
<store-dir>/
  AB/
    CD/
      ABCDEF…fingerprint.block.json
      ABCDEF…fingerprint.sig.<sighash>.json
      ABCDEF…fingerprint.revoke.json
```

Writes are atomic: write to `<path>.tmp`, then `os.rename()` into place. Reads rehydrate a full `Block` by:

1. Reading `<fp>.block.json`
2. Globbing all `<fp>.sig.*.json` files in the same directory
3. Following `prev_hash` links to order SigEntries
4. Assembling the final `Block` with its sig chain

An LRU cache (`cachetools.LRUCache`, default 128 entries) sits in front of the directory tree. Cache entries hold fully assembled blocks including their sig chains. The cache is populated on first access and on enumeration.

There is no startup scan and no index. Enumeration (`GET /blocks`, search) walks the directory tree.

### P2P layer

`gpgchain/p2p/` handles:

- **Peer registration** — reciprocal reachability check (`GET /peers` on the candidate), private IP rejection, peer list cap
- **Gossip** — forwarding new blocks/sigs/revocations to K random peers; seen-set (keyed by event hash, 1-hour TTL) prevents loops
- **Sync** — exchange `{fingerprint: sig_chain_head}` maps; fetch and verify missing material
- **Cross-validation** — periodic diff of hash maps across all peers; log discrepancies

### Trust layer

`gpgchain/trust/` implements the BFS algorithm from `spec/trust.md`:

- `build_graph(blocks)` — constructs the adjacency map and revoked set
- `score(target_fp, root_fp, graph, revoked_set, max_depth)` — path-counting BFS
- `trusted_set(root_fp, blocks, max_depth, threshold)` — all fingerprints with score ≥ threshold

---

## Go implementation

**Location:** `implementations/go/`

### HTTP layer — net/http + chi

`internal/api/api.go` uses `chi` for routing. Route handlers call into the chain, store, and P2P packages. All request/response types are defined as Go structs with `json` tags. Error responses are `{"error": "..."}`.

### Chain layer

`internal/chain/` mirrors the Python chain layer:

- `Block` and `SigEntry` structs
- `ComputeBlockHash` and `ComputeSigEntryHash` using `crypto/sha256`
- Payload construction helpers (`SubmitPayload`, `TrustPayload`, `RevokePayload`)

### GPG layer

`internal/gpg/gpg.go` uses `github.com/ProtonMail/go-crypto`:

- `ParseKey(armored)` — returns fingerprint and UIDs
- `VerifySelfSig`, `VerifyTrustSig`, `VerifyRevocationSig` — verify typed binary payloads
- `Sign(payload, armoredPrivKey)` — DetachSign over arbitrary payload, returns base64

The Go implementation uses `ProtonMail/go-crypto` rather than the standard library's `golang.org/x/crypto/openpgp` (deprecated) for full OpenPGP support including modern key types (Ed25519, ECDSA).

### Store layer — SQLite

`internal/store/` uses `modernc.org/sqlite` (pure Go, no CGo). Schema:

```sql
CREATE TABLE blocks (
    fingerprint TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    armored_key TEXT NOT NULL,
    uids        TEXT NOT NULL,   -- JSON array
    submit_ts   INTEGER NOT NULL,
    self_sig    TEXT NOT NULL,
    sig_chain_head TEXT NOT NULL DEFAULT '',
    revoked     INTEGER NOT NULL DEFAULT 0,
    revocation_sig TEXT NOT NULL DEFAULT ''
);

CREATE TABLE sig_entries (
    hash              TEXT PRIMARY KEY,
    block_fingerprint TEXT NOT NULL REFERENCES blocks(fingerprint),
    prev_hash         TEXT NOT NULL,
    signer_fp         TEXT NOT NULL,
    sig               TEXT NOT NULL,
    timestamp         INTEGER NOT NULL,
    signer_armored_key TEXT NOT NULL DEFAULT '',
    source_node       TEXT NOT NULL DEFAULT ''
);

CREATE INDEX sig_entries_block ON sig_entries(block_fingerprint);
CREATE INDEX blocks_uid ON blocks(uids);  -- JSON index for search
```

All writes use ACID transactions. Enumeration and fingerprint lookup are O(1) indexed reads. UID search uses a JSON function or a secondary index depending on the SQLite version.

### P2P layer

`internal/p2p/p2p.go` — same logical structure as Python. Uses goroutines for concurrent gossip forwarding and background sync. A `sync.Map` serves as the seen-set.

### Trust layer

`internal/trust/` implements both scoring algorithms:

- `Build(blocks)` → `Graph` (adjacency map + revoked set)
- `Score(g, targetFP, rootFP, maxDepth)` — standard path-counting BFS
- `DisjointScore(g, targetFP, rootFP, maxDepth)` — vertex-disjoint max-flow (node splitting + Edmonds-Karp)
- `TrustedSet(g, rootFP, maxDepth, threshold)` — all fingerprints with Score ≥ threshold

### CLI client

`cmd/client/main.go` implements nine commands as separate `flag.FlagSet` instances dispatched from `main()`. Environment variables (`GPGCHAIN_SERVER`, `GPGCHAIN_KEYID`) provide defaults for all server and identity flags.

Commands: `add`, `show`, `sign`, `revoke`, `list`, `check`, `search`, `verify`, `endorse`.

See `docs/cli-reference.md` for full flag documentation.

### Discovery package

`internal/discovery/` implements cross-ledger block discovery:

- `FindBlock(fp, TrustConfig, seeds)` — three-queue BFS (exact-domain → allow-all → others); optionally terminates early when trust threshold is met
- `FindBlocksByEmail(email, seeds)` — finds all blocks matching an email across multiple ledger nodes

The BFS prioritises nodes that have declared the target domain in their `/.well-known/gpgchain.json`, falling back to allow-all nodes, then all others.

---

## Data flow: submitting a block

```
Client
  │  POST /block {armored_key, self_sig, submit_ts}
  ▼
HTTP layer
  │  parse request, validate JSON
  ▼
GPG layer
  │  ParseKey → fingerprint, UIDs
  │  VerifySelfSig → ok/fail
  ▼
Store layer
  │  check fingerprint not already present
  │  ComputeBlockHash
  │  write block atomically
  ▼
P2P layer
  │  gossip to K random peers (async)
  ▼
HTTP layer
  │  200 {"hash": "...", "fingerprint": "..."}
```

---

## Data flow: trust evaluation (client-side)

```
CLI (list --keyid ROOT --min-trust 2 --disjoint)
  │  GET /blocks from server
  ▼
Trust layer
  │  Build(blocks) → Graph
  │  for each block:
  │    DisjointScore(g, fp, rootFP, maxDepth)
  │    if score >= threshold: include in output
  ▼
CLI
  │  print matching blocks
```

Trust evaluation never touches the server beyond the initial `GET /blocks`. All graph computation is local.

---

## Testing

All behaviour is tested via the Gherkin test suite in `tests/features/`. Tests are purely black-box HTTP — they communicate with a running server via the HTTP API and never inspect internal state.

CLI-specific behaviour is tested via subprocess in `tests/features/cli-client.feature` and `tests/features/cli-endorse.feature` (tagged `@cli`).

Both implementations must pass all non-skipped scenarios in `tests/features/`.
