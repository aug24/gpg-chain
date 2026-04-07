# GPG Chain

## Design Philosophy

**Always choose the most secure option.** When there is a trade-off between convenience and security, security wins. This applies to cryptographic choices (algorithm strength, key sizes, hash functions), API design (what the server accepts and validates), trust decisions (what is validated client-side vs trusted from the network), and dependency choices (minimal attack surface).

**Trust decisions belong to the client, always.** The server is a store and retrieval mechanism for cryptographic material. It has no concept of trust. It never evaluates, scores, filters, or expresses an opinion on whether any key should be trusted. Any feature that would require the server to reason about trust is out of scope for the server and must be implemented in the client.

**Spec first.** The canonical definition of this system lives in `spec/`. Implementations are secondary. Any behaviour not described in the spec is undefined. Any behaviour contradicting the spec is a bug.

**Language-agnostic.** The HTTP API and P2P protocol are defined independently of any implementation. Multiple implementations can coexist and interoperate on the same network. The Python implementation is the reference (clarity over performance); the Go implementation targets production use.

---

## What It Is

A distributed, append-only ledger where each entry contains a GPG public key. Participants add their own key, sign others' keys to express trust, and evaluate the web of trust locally. Designed for key discovery: given your own key as a root of trust, you can find and evaluate keys you've never seen before by following the trust graph — across ledger boundaries if necessary.

---

## Specifications (`spec/`)

| File | Contents |
|---|---|
| `openapi.yaml` | Canonical HTTP API definition — all public and peer endpoints, request/response schemas, error codes |
| `data-model.md` | Block and SigEntry structure, field definitions, hash computation |
| `payloads.md` | Binary signing payload formats for submission, trust, and revocation |
| `trust.md` | Trust graph algorithm — multi-hop BFS, scoring, cycle detection, revoked-node handling, cross-ledger traversal |
| `p2p.md` | P2P gossip protocol, sync procedure, peer exchange, cross-validation |

All spec documents are the source of truth. Implementations must conform to them.

---

## Core Concepts

- **Block**: a single GPG public key (ASCII-armored) plus a linked chain of trust signatures from other participants
- **Ledger**: a content-addressed DAG of blocks — each block is identified by the SHA-256 of its immutable content; there is no index-based ordering and no length-based consensus
- **Adding a key**: submit your armored public key plus a self-signature proving you control the corresponding private key; nodes gossip the block to peers
- **Signing a key**: submit a detached GPG signature over a typed binary payload identifying the target block; the signer may be on-ledger or off-ledger (see Off-Ledger Signatures)
- **Revoking a key**: submit a detached GPG signature over a typed binary revocation payload; only the key owner can revoke; revocation is permanent and gossiped
- **Trust evaluation**: purely client-side; never delegated to the server; your own key is the sole root of trust; trust traversal may cross ledger boundaries via off-ledger signers and their source nodes

---

## Domain Allowlist

Each node is configured with a set of permitted email domains. Only keys whose UIDs include at least one email address matching a permitted domain are accepted.

- If the allowlist is empty the node accepts nothing — an explicit `allow_all: true` config flag is required to accept all domains
- Keys with no email UID are always rejected
- A key passes if *any* of its UIDs contains a matching email domain
- The domain filter applies to both direct submissions and gossiped blocks — a node will not store or forward blocks outside its allowlist regardless of source
- Domain filtering is organisational scoping only; it does not verify that the submitter controls the email address (GPG UIDs are self-asserted)
- Two nodes with non-overlapping domain configs form isolated ledgers that speak the same protocol but share no blocks

---

## Block Structure

```
Block {
    Hash            string    // SHA-256 of (Fingerprint | ArmoredKey | SelfSig) — block identity
    Fingerprint     string    // uppercase hex, no spaces
    ArmoredKey      string    // ASCII-armored public key
    UIDs            []string  // extracted from the key for display/search
    SubmitTimestamp int64     // unix seconds — set by client, authenticated via SelfSig
    SelfSig         string    // base64 detached GPG sig proving submitter controls the private key
    SigChainHead    string    // hash of the most recent SigEntry (empty if no trust signatures yet)
    Revoked         bool
    RevocationSig   string    // base64 detached GPG sig over revocation payload (if revoked)
}

SigEntry {
    Hash              string  // SHA-256 of (PrevHash | SignerFingerprint | Sig | Timestamp)
    PrevHash          string  // hash of the previous SigEntry, or block Hash if first signature
    SignerFingerprint string
    Sig               string  // base64 detached GPG sig over the trust signing payload
    Timestamp         int64   // unix seconds — set by client, authenticated via Sig
    // Off-ledger only (omitted for on-ledger signers):
    SignerArmoredKey  string  // armored public key of the signer, stored inline for future verification
    SourceNode        string  // URL of the ledger node where the signer's block lives
}
```

Signatures form a per-block linked list anchored to the block hash. Any node that strips or reorders a signature breaks the chain, making tampering detectable.

`SubmitTimestamp` is not included in the block hash — it is authenticated indirectly via `SelfSig`. Nodes must not set or modify the timestamp.

---

## Off-Ledger Signatures

A signer does not need a block on the local ledger. An off-ledger signer provides their armored public key alongside the signature. The node verifies the signature at submission time and stores the key inline in the `SigEntry`.

- `SignerArmoredKey` — stored so any future client can re-verify the signature without fetching the key from elsewhere
- `SourceNode` — URL of the external ledger where the signer's block and their own signers can be found; provided by the submitter; used by clients for cross-ledger trust traversal
- Off-ledger signatures are subject to the same minimum key strength requirements as on-ledger keys
- The target block must still be on the local ledger and within the domain allowlist

---

## Signing Payloads

All payloads are typed binary strings — never JSON. Domain separation prevents any payload type from being confused with another.

| Purpose | Payload |
|---|---|
| Self-signature (submission) | `GPGCHAIN_SUBMIT_V1\x00<fingerprint>\x00<sha256_of_armored_key>\x00<timestamp>` |
| Trust signature | `GPGCHAIN_TRUST_V1\x00<block_hash>\x00<signer_fingerprint>\x00<timestamp>` |
| Revocation | `GPGCHAIN_REVOKE_V1\x00<fingerprint>\x00<block_hash>` |

All hex values are uppercase, no spaces. `\x00` is a literal null byte separator. Timestamps are decimal ASCII unix seconds.

---

## Trust Model

**Trust decisions are always made by the client.** The server provides cryptographic material; the client decides what to trust.

- **Root of trust**: your own key only — supplied via `--keyid` or `GPGCHAIN_KEYID`; never inferred from the network
- **Multi-hop**: trust propagates transitively; configurable max depth (default 2)
- **Scoring**: trust score for a target key = number of distinct non-revoked paths from your root to that key within the depth limit
- **Threshold**: configurable (default 1); a key is "trusted" if score ≥ threshold
- **Revoked keys are dead ends**: a revoked key contributes no paths, even if it has valid signatures on it
- **Off-ledger signers**: visible in the trust graph; can close a path if the client already has them in their local GPG keyring as trusted, or if traversal via `SourceNode` establishes their trustworthiness
- **Cross-ledger traversal**: when an off-ledger signer has a `SourceNode`, the client may fetch that node's ledger and continue trust traversal recursively; depth limit applies across ledger boundaries

---

## Cross-Ledger Discovery

Nodes advertise themselves via a well-known endpoint:

```
GET /.well-known/gpgchain.json
```

Response:
```json
{
  "node_url": "https://keys.example.com",
  "domains": ["example.com", "subsidiary.example.com"],
  "peers": ["https://keys.partner.org"]
}
```

This allows clients to discover which node holds keys for a given email domain. When evaluating an off-ledger signer, the client can:

1. Use the `SourceNode` URL from the `SigEntry` directly, or
2. Derive the node URL from the signer's email domain via `/.well-known/gpgchain.json`

Cross-ledger traversal is always client-initiated and client-controlled. Nodes never fetch from other nodes on a client's behalf.

---

## Ledger / Consensus

- Blocks are identified by their content hash — there is no index, no "longest chain"
- Valid state = the union of all independently verifiable blocks across all peers
- Two nodes can have different subsets of blocks; sync = exchange known hashes, request missing blocks
- A block is valid if: self-sig verifies against its own key, all referenced sig chain entries are present and hash-linked correctly, and all UIDs satisfy the node's domain allowlist
- Forks do not exist: each block is uniquely keyed by fingerprint; the first accepted wins network-wide
- Nodes cross-validate by fetching `{block_hash → SigChainHead}` maps from multiple peers to detect both block censorship and sig chain truncation

---

## Security Properties

| Threat | Mitigation |
|---|---|
| Submitter doesn't control the key | Self-signature required on submission |
| Malicious node rewrites history | Content-addressed blocks; no length-based consensus |
| Malicious node censors blocks or sigs | Cross-validate `{block_hash → SigChainHead}` maps across multiple peers |
| Stripped/reordered signatures | Per-block linked signature chain anchored to block hash |
| Fake web of trust (Sybil) | Multi-path threshold + depth limit in trust scoring |
| Payload type confusion | Typed domain-separated binary payloads with version prefix |
| Timestamp manipulation | Timestamps included in signed payloads; set by client not node |
| Eclipse attack via peer injection | Reciprocal reachability check; peer list cap; private IP rejection |
| Gossip amplification DoS | Bounded fanout (forward to K random peers, not all) |
| Domain pollution via gossip | Domain allowlist applied to all incoming blocks regardless of source |
| Off-ledger key too weak | Minimum key strength enforced on SignerArmoredKey at submission |
| Malicious SourceNode | Client verifies all cryptographic material independently; SourceNode is a hint only |

---

## P2P / Distribution

- Each node maintains a peer list (persistent, seeded via `--peers` flag)
- **Peer registration**: before accepting a new peer, node performs a reciprocal reachability check; rejects private/loopback addresses; caps peer list at a configured maximum
- **Gossip**: on receiving a new block, sig, or revocation, forward to K randomly selected peers (bounded fanout, default K=3); seen-set prevents loops; domain allowlist applied before forwarding
- **Sync on connect**: exchange `{block_hash → SigChainHead}` maps with each peer; fetch and verify any missing blocks or sig chain entries
- **Cross-validation**: periodically diff hash+head maps across all peers; warn on any discrepancy
- No proof-of-work; validity is purely cryptographic

---

## Implementations

### Python (`implementations/python/`) — Reference
- Clarity and correctness over performance
- FastAPI + Pydantic — clean data models, automatic OpenAPI validation
- `pgpy` for OpenPGP operations
- `cachetools.LRUCache` for bounded block cache
- Every spec behaviour is implemented as directly as possible; no optimisations that obscure intent

#### Python Store: Directory Tree
The store is a directory tree of immutable JSON files. No in-memory ledger is kept — disk is the source of truth.

**Layout** (default prefix depth 2+2, configurable via `--store-prefix-len`):
```
<store-dir>/
  AB/
    CD/
      ABCD...1234.block.json          # written once at submission; never modified
      ABCD...1234.sig.<sighash>.json  # one file per trust signature; immutable
      ABCD...1234.revoke.json         # written once on revocation; immutable
```

**Path derivation** — given fingerprint `FP` and prefix length `N` (default 4, split 2+2):
```
level1 = FP[0:2]
level2 = FP[2:4]
path   = <store-dir>/<level1>/<level2>/<FP>.<type>.json
```

**File types:**
| Suffix | Contents | Mutable? |
|---|---|---|
| `.block.json` | Full Block (no sig chain) | No — written once |
| `.sig.<sighash>.json` | Single SigEntry | No — written once |
| `.revoke.json` | RevocationSig + timestamp | No — written once |

**Writes** — each file is written atomically: write to `<path>.tmp`, then rename into place.

**Rehydration** — none required at startup. The first access to a block constructs its path from the fingerprint, reads the `.block.json` file, then reads all `.sig.*.json` files in the same directory that share the fingerprint prefix, orders them by following `PrevHash` links, and reconstructs the full block with its sig chain. Result is placed in the LRU cache.

**LRU cache** — configurable via `--cache-size` (default 128 blocks). Each cache entry holds one fully assembled Block including its sig chain. Eviction is LRU. Enumeration (`GET /blocks`, search) walks the directory tree and populates the cache as it goes.

**Startup** — the node verifies the store directory exists and is writable, then begins serving immediately. No scan, no pre-loading, no index.

### Go (`implementations/go/`) — Production
- Performance and deployment simplicity
- `ProtonMail/go-crypto` for OpenPGP
- `net/http` or `chi` for HTTP
- Goroutines for concurrent gossip and sync
- SQLite via `modernc.org/sqlite` (pure Go, no CGo) for the backing store
- ACID transactions; incremental writes; indexed lookups by fingerprint and UID

Both implementations must conform to `spec/openapi.yaml` and pass the same integration test suite.

---

## Project Layout

```
gpg-chain/
  spec/
    openapi.yaml             # Canonical HTTP API definition
    data-model.md            # Block, SigEntry, hash computation
    payloads.md              # Binary signing payload formats
    trust.md                 # Trust graph algorithm + cross-ledger traversal
    p2p.md                   # Gossip, sync, peer exchange protocol
  implementations/
    python/                  # Reference implementation
      gpgchain/
        api/                 # FastAPI routes
        chain/               # Block, SigEntry, ledger logic
        gpg/                 # Key parsing, sig verification, payload construction
        store/               # JSON file store + in-memory store
        p2p/                 # Gossip, sync, peer management
        trust/               # Trust graph evaluation + cross-ledger traversal
      node.py                # Node entrypoint
      client.py              # CLI client entrypoint
      requirements.txt
      pyproject.toml
    go/                      # Production implementation
      cmd/
        node/                # Node binary
        client/              # CLI client binary
      internal/
        chain/
        gpg/
        store/
        api/
        p2p/
        trust/               # Trust graph + cross-ledger traversal
      go.mod
      go.sum
  scripts/
    build.sh                 # Build all implementations
    cluster.sh               # Start/stop mixed Go+Python cluster
    clean.sh                 # Stop all nodes, remove data directories
  tests/
    features/                # Gherkin .feature files — language-agnostic, portable
      adding-keys.feature
      signing-keys.feature
      trust.feature
      revocation.feature
      p2p.feature
      search.feature
      domain-allowlist.feature
      off-ledger-signatures.feature
      cross-ledger.feature
    steps/                   # behave step definitions (Python + requests)
    support/                 # HTTP client wrapper, config, test key fixtures
    fixtures/                # Pre-generated GPG test keys and signed payloads
  docs/
    getting-started.md
    architecture.md
    new-implementation.md    # Guide for adding a third language
  CLAUDE.md
  TODO.md
```

---

## Tests

Tests are written in Gherkin (`.feature` files) and run with **`behave`** (Python). They are entirely black-box — they communicate with the server only via the HTTP API, with no knowledge of the implementation language.

The target server is set via `GPGCHAIN_TEST_SERVER` or `--server`:

```bash
# Run against the Python node
GPGCHAIN_TEST_SERVER=http://localhost:8080 behave tests/

# Run against the Go node
GPGCHAIN_TEST_SERVER=http://localhost:8081 behave tests/

# Run against a mixed cluster (tests pick nodes at random or by tag)
GPGCHAIN_TEST_SERVER=http://localhost:8080,http://localhost:8081 behave tests/
```

Feature files are the canonical description of correct behaviour. If a scenario contradicts `spec/openapi.yaml`, the spec wins. If the spec is ambiguous, the scenario clarifies it.

The `.feature` files are portable — they can be run with any Cucumber-compatible runner (`cucumber-js`, `godog`, etc.) if step definitions are rewritten. `behave` is the reference runner; the feature files are the durable artefact.

---

## Running a Local Cluster

```bash
# Build everything
./scripts/build.sh

# Start 3 Go nodes + 2 Python nodes (ports allocated from 8080 upward)
./scripts/cluster.sh start --go 3 --python 2

# Show running nodes
./scripts/cluster.sh status

# Stop all nodes
./scripts/cluster.sh stop

# Client (either language, any node)
gpgchain add    --server http://localhost:8080 --key pubkey.asc --keyid MYFINGERPRINT
gpgchain sign   --server http://localhost:8082 --fingerprint ABCD1234 --keyid MYFINGERPRINT
gpgchain list   --server http://localhost:8081 --keyid MYFINGERPRINT --min-trust 1
gpgchain check  --server http://localhost:8080 --fingerprint ABCD1234 --keyid MYFINGERPRINT
gpgchain verify --server http://localhost:8080
```

The cluster script wires all nodes together as peers. Any node can be used as the server target for any client command.

---

## Conventions

- All errors returned as `{"error": "..."}` JSON with appropriate HTTP status
- Fingerprints: uppercase hex, no spaces
- All signatures: base64-encoded detached binary OpenPGP signatures
- Signing payloads: typed binary strings (see `spec/payloads.md`) — never JSON
- Gossip messages carry the originating node address to prevent re-notification loops
- `--keyid` / `GPGCHAIN_KEYID` required for any command that involves signing or trust evaluation
- Minimum key strength: RSA ≥ 2048 bit; no DSA-1024; Ed25519 preferred
