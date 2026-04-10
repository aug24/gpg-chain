# GPG Chain — Go Implementation

This is the **production implementation** of GPG Chain. It targets lower memory use, faster startup, and deployment simplicity compared to the Python reference. It passes the same Gherkin test suite as the Python implementation.

---

## What it does

Same behaviour as the Python node — stores GPG public keys in a content-addressed ledger, gossips new entries to peers over HTTP, and exposes the REST API defined in `spec/openapi.yaml`. Trust evaluation is always client-side.

---

## Quick start

```bash
# Build (from implementations/go/)
go build -o gpgchain-node ./cmd/node/

# Run a node that accepts keys from any domain
./gpgchain-node --allow-all-domains

# Smoke test
curl http://localhost:8080/peers                    # → []
curl http://localhost:8080/.well-known/gpgchain.json
```

Run the test suite against it (Python `behave` from the repo root):

```bash
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/
# Expected: 11 features passed, 0 failed, 3 skipped
#           56 scenarios passed, 0 failed, 23 skipped
```

---

## Layout

```
implementations/go/
  cmd/
    node/main.go    Entry point: parse flags + env vars, open store, wire components, start server
    client/main.go  CLI client (stub — not yet complete)
  internal/
    chain/
      block.go      Block and SigEntry types; ComputeBlockHash; ComputeSigEntryHash
    gpg/
      gpg.go        ParseArmoredKey, CheckKeyStrength, ExtractEmailDomains,
                    SubmitPayload, TrustPayload, RevokePayload, VerifyDetachedSig
    store/
      store.go      Store interface
      memory.go     MemoryStore — in-memory, for tests
      sqlite.go     SQLiteStore — production store backed by modernc.org/sqlite
    p2p/
      p2p.go        PeerList, Gossip (fanout + seen-set), SyncWithPeer, CrossValidate
    trust/
      trust.go      Build, Score, IsTrusted, TrustedSet — client-side BFS trust evaluation
    api/
      api.go        Config struct, NewRouter, all HTTP handlers
  go.mod
  go.sum
```

---

## Key packages

### `internal/chain`
Defines `Block` and `SigEntry` structs and two hash functions.

**Block hash** = SHA-256(`fingerprint \x00 armored_key \x00 self_sig`), uppercase hex.

**SigEntry hash** = SHA-256(`prev_hash \x00 signer_fingerprint \x00 sig \x00 timestamp`), uppercase hex.

Both match the Python reference exactly.

### `internal/gpg`
All OpenPGP operations using `github.com/ProtonMail/go-crypto/openpgp` — no `gpg` subprocess.

- `ParseArmoredKey(armored) (fingerprint, uids, err)` — decode ASCII-armored public key
- `CheckKeyStrength(armored) error` — reject RSA < 2048 bit, DSA-1024
- `ExtractEmailDomains(uids) []string` — parse email domains from UID strings
- `SubmitPayload(fp, armoredKey, ts)` — `GPGCHAIN_SUBMIT_V1\x00fp\x00sha256(key)\x00ts`
- `TrustPayload(blockHash, signerFP, ts)` — `GPGCHAIN_TRUST_V1\x00blockHash\x00signerFP\x00ts`
- `RevokePayload(fp, blockHash)` — `GPGCHAIN_REVOKE_V1\x00fp\x00blockHash`
- `VerifyDetachedSig(payload, b64sig, armoredKey) bool` — verify a base64 detached binary sig

### `internal/store`

**Store interface** — six methods: `Add`, `Get`, `All`, `AddSig`, `Revoke`, `Hashes`.

**MemoryStore** — thread-safe in-memory map. Used by tests that require a fresh store per scenario. Returns deep copies to prevent aliasing.

**SQLiteStore** — `modernc.org/sqlite` (pure Go, no CGo). Single writer connection (`SetMaxOpenConns(1)`). Schema:
- `blocks` table — one row per block; `sig_chain_head` updated atomically with `AddSig`
- `sig_entries` table — one row per SigEntry; linked list reconstructed in `getSigEntries` by following `prev_hash` links

`Hashes()` is a cheap two-column SELECT — it does not load sig entries.

### `internal/p2p`

**PeerList** — thread-safe slice with a capacity cap. `Add` is idempotent (no-op if already present, error if at capacity).

**Gossip** — on receiving a new event, pick K=3 random peers (excluding the origin) and POST the event to each in a goroutine. A seen-set (keyed by event hash, TTL 1 hour) prevents forwarding the same event twice. Methods: `GossipBlock`, `GossipSig`, `GossipRevoke`.

**SyncWithPeer(peerURL, SyncConfig)** — fetch `GET /p2p/hashes` from peer; for each fingerprint the peer has that we don't, fetch and cryptographically verify the block before storing; for fingerprints where `sig_chain_head` differs, fetch the full block and apply missing sig entries; push our blocks that the peer is missing.

**CrossValidate(peers, store)** — compare local hash map against all peers; log and return fingerprints with discrepancies.

### `internal/trust`
Client-side trust graph evaluation. `Build(blocks)` constructs an adjacency map `fingerprint → set{signer fingerprints}`. Revoked blocks are present as nodes but have no outgoing edges (they cannot convey trust). `Score` counts distinct non-cyclic paths from `rootFP` to `targetFP` within `maxDepth` using BFS with per-path visited sets. `IsTrusted` = score ≥ threshold. `TrustedSet` returns all fingerprints above threshold.

### `internal/api`
`Config` holds all runtime state (store, gossip, peers, domain allowlist, flags). `NewRouter(cfg)` registers all routes on a `chi` router and returns the handler.

Handlers follow the same validation flow as the Python reference:
1. Decode JSON body
2. Validate required fields
3. Parse/verify the key
4. Check domain allowlist
5. Verify signature against typed binary payload
6. Write to store
7. Fire gossip goroutine
8. Return JSON response

---

## Node flags

| Flag | Env var | Default | Purpose |
|---|---|---|---|
| `--addr` | — | `0.0.0.0:8080` | Listen address |
| `--store` | `GPGCHAIN_STORE_DIR` | `./data/chain.db` | SQLite database path |
| `--allow-all-domains` | `GPGCHAIN_ALLOW_ALL=true` | off | Accept keys from any domain |
| `--domains` | `GPGCHAIN_DOMAINS` | (empty) | Comma-separated allowed domains |
| `--node-url` | `GPGCHAIN_NODE_URL` | (empty) | This node's public URL |
| `--peers` | — | (empty) | Bootstrap peer URLs |
| `--allow-private-peers` | `GPGCHAIN_ALLOW_PRIVATE_PEERS=true` | off | Skip private IP rejection (containers only) |
| `--max-peers` | — | `50` | Peer list capacity |

---

## Dependencies

| Module | Purpose |
|---|---|
| `github.com/ProtonMail/go-crypto` | OpenPGP operations |
| `github.com/go-chi/chi/v5` | HTTP router |
| `modernc.org/sqlite` | SQLite driver (pure Go, no CGo) |

All dependencies are pure Go — the binary can be cross-compiled without a C toolchain.

---

## Further reading

- `spec/openapi.yaml` — canonical HTTP API
- `spec/data-model.md` — block/SigEntry fields and hash computation
- `spec/payloads.md` — binary signing payload formats
- `spec/trust.md` — BFS trust algorithm
- `spec/p2p.md` — gossip, sync, cross-validation
- `implementations/python/` — reference implementation (read this if behaviour is unclear)
