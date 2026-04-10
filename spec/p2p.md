# P2P Protocol

This document defines the peer-to-peer gossip and synchronisation protocol for GPG Chain nodes. All inter-node communication uses the same HTTP API defined in `openapi.yaml`. There is no separate P2P wire protocol; all P2P endpoints are prefixed `/p2p/`.

---

## Overview

Each node participates in a gossip network without any central authority. Nodes maintain a list of known peer URLs, gossip new events (blocks, signatures, revocations) to a bounded random subset of peers, and synchronise their ledger state when they connect to a peer. Validity is purely cryptographic — there is no proof-of-work and no consensus vote. A block is valid if its signatures verify; a valid block from any source is stored.

---

## Peer Registration

### POST /peers

Request body: `{"addr": "<url>"}`

A node registers a new peer by sending a POST request to `/peers`. The receiving node applies the following acceptance rules in order. All rules must pass; failure at any step rejects the registration.

**Rule 1 — URL scheme:** The `addr` field must be a valid URL with scheme `http` or `https`. Any other scheme (including empty, `ftp`, `ws`, etc.) is rejected with HTTP 400.

**Rule 2 — No private or loopback addresses:** The host in the URL must not resolve to any address in the following ranges:
- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`
- `127.0.0.0/8`
- `::1` (IPv6 loopback)
- `fc00::/7` (IPv6 unique local)

A node that resolves to any of these ranges is rejected with HTTP 400. This prevents SSRF and eclipse attacks via internal network injection.

**Rule 3 — Reciprocal reachability check:** The receiving node must perform a `GET /peers` request to the claimed `addr`. If this request does not return HTTP 200 within a reasonable timeout (implementation-defined, suggested 5 seconds), the registration is rejected with HTTP 400. This confirms the peer is reachable and is running a compatible node.

**Rule 4 — Peer list capacity:** The peer list has a configurable maximum size (default 50 peers). If the peer list is already at capacity, return HTTP 429. The new peer is not added.

**Rule 5 — Deduplication:** If the claimed `addr` is already in the peer list, silently accept it (return HTTP 200) without adding a duplicate entry.

### Reciprocal Registration

After successfully accepting a new peer, the receiving node should also register itself with the new peer by sending `POST /peers` with its own node URL to the peer's `/peers` endpoint. This makes peer discovery bidirectional. Failure of this reciprocal registration is non-fatal and does not affect the local acceptance of the peer.

---

## Gossip Protocol

### Triggering Gossip

Gossip is triggered when a node accepts any of the following new events — whether from a direct client submission or from an incoming `/p2p/*` endpoint:

- A new Block (via `POST /block` or `POST /p2p/block`)
- A new SigEntry (via `POST /block/:fingerprint/sign` or `POST /p2p/sign`)
- A new revocation (via `POST /block/:fingerprint/revoke` or `POST /p2p/revoke`)

### Fanout

The node selects K peers at random from its peer list (default K = 3). If fewer than K peers are known, all known peers are selected. The node sends the event to each selected peer concurrently.

### Gossip Message Format

Each gossip message carries:
- The full event payload as defined for the relevant `/p2p/*` endpoint.
- `origin`: the URL of the node that first accepted the event (not the forwarding node's URL). This is included to allow receiving nodes to identify the source of new material.

For blocks, the full Block object (all fields) is included. For signatures, the fingerprint of the target block and the full SigEntry are included. For revocations, the fingerprint and revocation signature are included. See `openapi.yaml` for exact request body schemas.

### Seen-Set

Each node maintains an in-memory seen-set of event IDs to prevent forwarding the same event more than once.

**Event IDs:**
- Block event: the block's `hash` field (64-char uppercase hex).
- SigEntry event: the SigEntry's `hash` field (64-char uppercase hex).
- Revocation event: the fingerprint concatenated with the literal string `.revoke` (e.g. `ABCDEF1234....revoke`).

**Before forwarding:**
1. Compute the event ID.
2. Check if it is in the seen-set.
3. If present: drop the event silently. Do not forward.
4. If absent: add to the seen-set, then forward to K random peers.

**Expiry:** Seen-set entries expire after 1 hour. This bounds memory usage and allows re-propagation of very old events if needed (though in practice this should not occur).

### Receiving a Gossiped Event

When a gossiped event arrives via `/p2p/block`, `/p2p/sign`, or `/p2p/revoke`:

1. **Validate:** Apply the same full validation as for a direct client submission. This includes:
   - For blocks: verify `self_sig` against the submitted key and the SUBMIT payload; verify `hash` computation; enforce key strength requirements.
   - For SigEntries: verify the SigEntry's `hash` computation; verify the `sig` against the TRUST payload; verify the `prev_hash` link.
   - For revocations: verify the `revocation_sig` against the REVOKE payload using the block's own key.
2. **Domain allowlist:** Apply the node's configured domain allowlist. Blocks (and their associated gossip) for keys outside the allowlist are rejected and not stored. This applies regardless of whether the block came from a direct client or from a gossip peer.
3. **Already seen:** Check the seen-set. If already seen, return HTTP 200 without re-storing or re-forwarding.
4. **Store:** If valid and not already seen, store the event.
5. **Gossip forward:** Add to the seen-set, then gossip to K more random peers.
6. **Invalid event:** Return HTTP 400, do not store, do not forward.

---

## Sync on Connect

When a node starts up or establishes a connection to a known peer, it performs the following synchronisation procedure with that peer:

### Step 1 — Register self

Send `POST /peers` with the local node's own URL to the peer. This ensures the peer knows about the local node.

### Step 2 — Fetch peer's hash map

Send `GET /p2p/hashes` to the peer. This returns a JSON object mapping fingerprints to their `sig_chain_head` values for all blocks the peer knows about.

```json
{
  "ABCDEF1234567890ABCDEF1234567890ABCDEF12": "F1E2D3C4...",
  "FEDCBA0987654321FEDCBA0987654321FEDCBA09": ""
}
```

### Step 3 — Diff and fetch missing blocks

Compare the peer's hash map against the local store:

**3a — Fingerprints the peer has but the local node does not:**
For each such fingerprint, fetch the full Block by sending `GET /p2p/block/<block_hash>` where `block_hash` is the value from the peer's hash map. Verify the block (hash computation, self-sig, domain allowlist). If valid, store it locally. Also store any SigEntries embedded in the block's sig chain.

Note: use the block hash (value) not the fingerprint (key) for the fetch URL. This ensures the fetched block matches the content the peer advertised.

**3b — Fingerprints present on both nodes but with different `sig_chain_head`:**
Fetch the full Block from the peer. Compare sig chains. For each SigEntry in the peer's chain that is not present locally, verify it and store it. A SigEntry is missing locally if following the local `prev_hash` chain from the local `sig_chain_head` does not reach it.

### Step 4 — Reverse sync

After fetching from the peer, gossip any blocks to the peer that the peer was missing (those in the local store but not in the peer's hash map).

### Verification During Sync

Every piece of data received from a peer during sync is subject to full cryptographic verification before storage:
- Block hash must match the SHA-256 computed from the block's fields.
- Block self-sig must verify against the block's key and the SUBMIT payload.
- Every SigEntry hash must match the SHA-256 computed from its fields.
- Every SigEntry sig must verify against the appropriate key and the TRUST payload.
- Domain allowlist must be satisfied.

Invalid data from peers is silently discarded. Sync continues with the remaining items.

---

## Cross-Validation

To detect block censorship and sig chain truncation, each node periodically cross-validates its state against all known peers.

**Default interval:** 60 seconds.

### Procedure

1. For each known peer, fetch `GET /p2p/hashes`. Handle network failures gracefully — a failed fetch for one peer does not abort cross-validation for other peers.
2. For each fingerprint across all peers:
   - **Peer has a different `sig_chain_head` than the local node:** The peer may have more SigEntries. Fetch the peer's full block and compare sig chains. Apply any SigEntries the local node is missing (with full verification). Log a warning noting that the local node had fewer signatures than a peer for this fingerprint.
   - **Peer is missing a fingerprint that the local node has:** Possible network partition or the peer hasn't received this block yet. Log a warning for operator visibility. The block may propagate via later gossip or sync.
   - **Fingerprint only the local node has (peer has never seen it):** Log a warning. Offer the block to the peer by gossiping it.
3. Log all discrepancies at WARNING level with the peer URL and fingerprint involved. These logs are for operator visibility; the node takes no automated action beyond fetching fuller sig chains.

---

## /p2p/hashes Response Format

`GET /p2p/hashes` returns a JSON object where each key is a fingerprint (uppercase hex string) and each value is the current `sig_chain_head` for that block (uppercase hex string, or empty string if no trust signatures exist).

```json
{
  "ABCDEF1234567890ABCDEF1234567890ABCDEF12": "F1E2D3C4B5A6978869504132ABCDEF9876543210FEDCBA01234567890ABCDEF12",
  "FEDCBA0987654321FEDCBA0987654321FEDCBA09": "",
  "1234567890ABCDEF1234567890ABCDEF12345678": "AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00112233445566778899"
}
```

An empty string value means the block has no trust signatures yet (its `sig_chain_head` is `""`).

This endpoint is intentionally lightweight. It returns only fingerprints and chain heads, not full block content, to allow efficient diffing between nodes.

---

## Peer Health Tracking

To avoid repeatedly attempting to contact unreachable peers, each node tracks the health of its peer connections.

**Failure counting:** Each peer has an associated consecutive failure counter, initialised to 0. Any HTTP request to a peer that results in a network error, timeout, or HTTP 5xx response increments the counter. A successful response (HTTP 2xx) resets the counter to 0.

**Marking unhealthy:** After 5 consecutive failures, the peer is marked as unhealthy. Unhealthy peers are excluded from gossip fanout selection and from cross-validation fetches.

**Retry interval:** Unhealthy peers are retried every 5 minutes. A single successful response on retry marks the peer as healthy again (counter reset to 0).

**Removal:** Peers that have been continuously unhealthy for 24 hours are removed from the peer list entirely. They may be re-added later via the normal `POST /peers` registration flow.

**Persistence:** The peer list (including health state) should be persisted to disk so that it survives node restarts. The specific persistence mechanism is implementation-defined.
