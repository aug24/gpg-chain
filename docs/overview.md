# How GPG Chain works

This document explains the purpose of the system, the core concepts, and the key design decisions. It is meant to be read before diving into the specifications or the code.

---

## The problem

GPG's web of trust has always had a discovery problem. You can sign someone's key to vouch for it, and others can do the same, but there is no good way to find keys you have not already encountered, or to evaluate whether a key you just received is trustworthy.

Key servers (SKS, keys.openpgp.org) solve the discovery part but not the trust part — they are neutral stores with no concept of who vouches for whom. The GPG web of trust is rich in theory but requires out-of-band synchronisation (key-signing parties, manual imports) to be useful in practice.

GPG Chain addresses this by combining key storage with an explicit, auditable trust graph. Participants publish their key to a ledger, sign other participants' keys to express trust, and evaluate the resulting graph locally using their own key as the sole root of trust.

---

## Core concepts

### Blocks

Each entry in the ledger is called a **block**. A block contains one GPG public key in ASCII-armored form, plus metadata:

- The key's **fingerprint** (uppercase hex, no spaces)
- The **UIDs** extracted from the key (for search and domain filtering)
- A **self-signature** — a detached GPG signature over a typed binary payload that proves the submitter controls the corresponding private key
- A **submit timestamp**, set by the client and authenticated by the self-signature

Blocks are **content-addressed**: each block's identity is the SHA-256 of its fingerprint, armored key, and self-signature. A block cannot be modified after submission. There is no index-based ordering — the ledger is a set of independently verifiable objects, not a chain of blocks in the blockchain sense.

### The signature chain

After a block is submitted, other participants can **sign** it to express trust. Each trust signature is a **SigEntry** appended to the block's signature chain. SigEntries form a linked list anchored to the block hash:

```
Block hash ← SigEntry 1 ← SigEntry 2 ← SigEntry 3 (sig_chain_head)
```

Each SigEntry contains the signer's fingerprint, a detached signature over a typed binary payload, a timestamp, and a pointer back to the previous entry. This linking makes the chain tamper-evident: a node that strips or reorders a signature breaks the chain, and the discrepancy is detectable by any client that compares `sig_chain_head` values across peers.

### Signing payloads

All signatures are over **typed binary payloads** — never over JSON. Domain separation prevents a signature created for one purpose from being replayed as another:

| Purpose | Payload prefix |
|---|---|
| Self-signature on submission | `GPGCHAIN_SUBMIT_V1\x00` |
| Trust signature | `GPGCHAIN_TRUST_V1\x00` |
| Revocation | `GPGCHAIN_REVOKE_V1\x00` |

### Revocation

The key owner can revoke their block at any time by submitting a detached signature over a revocation payload. Revocation is permanent. A revoked block remains retrievable (for audit purposes) but is a dead end in trust traversal — no paths flow through a revoked key.

### Off-ledger signatures

A signer does not need their own block on the local ledger. An **off-ledger signer** provides their armored public key inline alongside the trust signature. The node verifies the signature at submission time and stores the key in the SigEntry for future verification. An optional `source_node` URL indicates where the signer's own block lives, enabling cross-ledger trust traversal by clients.

---

## Trust evaluation

**Trust decisions belong entirely to the client.** The server stores and serves cryptographic material; it never evaluates, scores, or filters based on trust.

The client's trust model:

1. **Root of trust** — your own key only, supplied explicitly. Never inferred from the network.
2. **Multi-hop BFS** — trust propagates transitively up to a configurable depth (default 2). Alice trusts Bob; Bob signed Carol; therefore Alice can reach Carol in 2 hops.
3. **Scoring** — a key's trust score is the number of distinct non-revoked paths from your root to that key within the depth limit.
4. **Threshold** — configurable (default 1). A key is considered trusted if its score meets or exceeds the threshold.
5. **Revoked keys are dead ends** — a revoked key contributes no paths, even if it has valid signatures on it.
6. **Cross-ledger traversal** — when an off-ledger signer has a `source_node` URL, the client may fetch that node's ledger and continue BFS recursively. The depth limit applies across ledger boundaries.

---

## The ledger

The ledger is a **content-addressed DAG** — not a blockchain. There is no proof-of-work, no longest-chain rule, and no global ordering. Valid state is the union of all independently verifiable blocks across all peers.

- Two nodes can have different subsets of blocks; sync exchanges what each is missing.
- A block is valid if its self-signature verifies, all referenced SigEntries are present and hash-linked correctly, and the key's UIDs satisfy the node's domain allowlist.
- Forks do not exist: each block is uniquely keyed by fingerprint; the first valid submission wins.

### Domain allowlist

Each node is configured with a set of permitted email domains. Only keys whose UIDs include at least one matching email address are accepted. An explicit `allow_all` flag is required to accept keys from any domain. The allowlist applies to both direct submissions and gossiped blocks.

This is an organisational scoping mechanism, not an identity verification mechanism. GPG UIDs are self-asserted; the node does not verify that the submitter controls the email address.

---

## P2P distribution

### Peer registration

Nodes maintain a peer list. Before accepting a new peer, a node performs a **reciprocal reachability check** (GET /peers on the candidate) and rejects any address that resolves to a private or loopback IP. The peer list is capped to prevent unbounded growth. After accepting a peer, the node registers itself with that peer and initiates a sync.

### Gossip

When a node accepts a new block, trust signature, or revocation — from a client or from another node — it forwards the event to K randomly selected peers (default K=3). An in-memory **seen-set** (keyed by event hash, expiring after 1 hour) prevents the same event from being forwarded more than once. This bounds the number of network messages for any single event at O(K × diameter).

### Sync on connect

When a node connects to a peer it:

1. Fetches the peer's `GET /p2p/hashes` — a map of `{fingerprint: sig_chain_head}`.
2. Fetches any blocks or SigEntries the peer has that it does not.
3. Pushes any blocks it has that the peer is missing.

Every piece of data received during sync is fully cryptographically verified before storage.

### Cross-validation

Nodes periodically compare their `{fingerprint: sig_chain_head}` map against all peers. A discrepancy indicates either that the local node is missing SigEntries (fixable by fetching the longer chain) or that a peer is missing a block entirely (logged as a warning). This makes it detectable — though not preventable — for a malicious node to censor blocks or strip signatures.

---

## Security properties

| Threat | Mitigation |
|---|---|
| Submitter doesn't control the key | Self-signature required on submission |
| Malicious node rewrites history | Content-addressed blocks; no length-based consensus |
| Malicious node censors blocks or sigs | Cross-validate `{fingerprint: sig_chain_head}` maps across multiple peers |
| Stripped or reordered signatures | Per-block linked chain anchored to block hash |
| Sybil attack on trust | Multi-path threshold + depth limit in trust scoring |
| Payload type confusion | Typed domain-separated binary payloads with version prefix |
| Timestamp manipulation | Timestamps included in signed payloads; set by client, not node |
| Eclipse attack via peer injection | Reciprocal reachability check; private IP rejection; peer list cap |
| Gossip amplification DoS | Bounded fanout; seen-set prevents forwarding loops |
| Domain pollution via gossip | Domain allowlist applied to all incoming blocks regardless of source |

---

## Implementation strategy

The **Python implementation** (`implementations/python/`) is the reference. It is written for clarity and direct correspondence with the spec, not for performance. It uses:

- **FastAPI** for the HTTP layer
- **pgpy** for all OpenPGP operations (no `gpg` subprocess, no gpg-agent)
- A **directory tree store** — one JSON file per block, one per SigEntry, one per revocation — with an LRU cache in front

The **Go implementation** (`implementations/go/`) targets production use: lower memory, faster startup, SQLite-backed store, concurrent gossip.

Both implementations must pass the same Gherkin test suite in `tests/features/`. The feature files are the compliance specification; if a scenario contradicts the spec, the spec wins.

---

## Further reading

- `spec/openapi.yaml` — every HTTP endpoint, request schema, response schema, and error code
- `spec/data-model.md` — exact field definitions and hash computation
- `spec/payloads.md` — binary signing payload formats with worked examples
- `spec/trust.md` — BFS algorithm, scoring, cycle detection, cross-ledger traversal
- `spec/p2p.md` — gossip fanout, sync procedure, peer health tracking, cross-validation
- `docs/getting-started.md` — install, run, test
