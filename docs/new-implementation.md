# Adding a New Implementation

This guide walks through building a new GPG Chain node in a language other than Python or Go.

---

## What you are building

A GPG Chain node is an HTTP server that:

1. Accepts GPG public keys from clients (with cryptographic proof of ownership)
2. Accepts trust signatures from clients (expressing that one key vouches for another)
3. Accepts revocations from clients (invalidating a key permanently)
4. Gossips new material to peer nodes
5. Syncs with peers on connect
6. Responds to read queries (get block, list blocks, search, hash map for sync)

It does **not** evaluate trust. Trust is entirely client-side.

The canonical definition of all behaviour is in `spec/`. Start there before writing any code.

---

## Step 1: Read the specifications

Read the spec documents in this order:

1. `spec/data-model.md` — Block and SigEntry structure, hash computation
2. `spec/payloads.md` — Binary signing payload formats
3. `spec/openapi.yaml` — Every HTTP endpoint, request and response schema, error codes
4. `spec/trust.md` — The trust algorithm (client-side; you don't implement this in the node, but you need it for the CLI)
5. `spec/p2p.md` — Gossip, sync, peer exchange

The OpenAPI spec is the contract. Implement it exactly. Do not add or remove fields.

---

## Step 2: Choose a GPG library

You need an OpenPGP library that can:

- Parse ASCII-armored public keys (extract fingerprint, UIDs, key material)
- Verify detached binary signatures (not clearsigned, not armored — raw binary sig over raw binary payload)
- Create detached binary signatures (for the CLI client)
- Support Ed25519 and RSA-2048+ keys; reject DSA-1024

Avoid calling the `gpg` binary as a subprocess. That introduces gpg-agent dependency, keyring pollution, and unreliable output parsing. Use a library that operates directly on key material.

Minimum key strength: RSA ≥ 2048 bit; no DSA-1024; Ed25519 preferred.

---

## Step 3: Implement hash computation

Block hash: `SHA-256(fingerprint_bytes + null + armored_key_bytes + null + self_sig_bytes)`

Wait — check `spec/data-model.md` for the exact byte layout. The spec is authoritative; this document is illustrative only.

SigEntry hash: `SHA-256(prev_hash_bytes + null + signer_fp_bytes + null + sig_bytes + null + timestamp_bytes)`

Again, `spec/data-model.md` is the source of truth.

Fingerprints are uppercase hex, no spaces. Timestamps are decimal ASCII unix seconds.

---

## Step 4: Implement signature verification

Three payload types (from `spec/payloads.md`):

- **SUBMIT** — `GPGCHAIN_SUBMIT_V1\x00<fingerprint>\x00<sha256_of_armored_key>\x00<timestamp>`
- **TRUST** — `GPGCHAIN_TRUST_V1\x00<block_hash>\x00<signer_fingerprint>\x00<timestamp>`
- **REVOKE** — `GPGCHAIN_REVOKE_V1\x00<fingerprint>\x00<block_hash>`

The `\x00` is a literal null byte (0x00). The hex values are uppercase ASCII. Timestamps are decimal ASCII.

The signature in each request is a base64-encoded detached binary OpenPGP signature. Decode it from base64 before passing it to your GPG library.

---

## Step 5: Implement the HTTP endpoints

Minimum required endpoints for compatibility:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/block` | Submit a new key |
| `GET` | `/block/{fingerprint}` | Fetch a single block with sig chain |
| `GET` | `/blocks` | List all blocks |
| `POST` | `/block/{fingerprint}/sign` | Append a trust signature |
| `POST` | `/block/{fingerprint}/revoke` | Revoke a block |
| `GET` | `/search` | Search by email UID |
| `GET` | `/peers` | List known peers |
| `POST` | `/peers` | Register a new peer |
| `GET` | `/p2p/hashes` | Return `{fingerprint: sig_chain_head}` map |
| `POST` | `/p2p/block` | Receive a gossiped block |
| `POST` | `/p2p/sig` | Receive a gossiped signature |
| `POST` | `/p2p/revoke` | Receive a gossiped revocation |
| `GET` | `/.well-known/gpgchain.json` | Node metadata for discovery |

All errors must be returned as `{"error": "..."}` JSON with an appropriate HTTP status code.

### Validation checklist for `POST /block`

1. Parse the armored key → fingerprint, UIDs
2. Check that at least one UID contains an email matching the domain allowlist (or `allow_all` is set)
3. Verify the self-signature against the SUBMIT payload
4. Check the fingerprint is not already stored
5. Compute the block hash
6. Store atomically
7. Gossip to K random peers

### Validation checklist for `POST /block/{fingerprint}/sign`

1. Fetch the existing block (404 if not found)
2. Check the block is not revoked
3. Determine signer's public key: if `signer_armored_key` provided (off-ledger), use it directly; otherwise fetch the signer's block from the local ledger
4. Verify the trust signature against the TRUST payload (`block_hash`, `signer_fingerprint`, `timestamp`)
5. Compute the SigEntry hash (prev_hash = current sig_chain_head or block hash if empty)
6. Store the SigEntry and update `sig_chain_head` atomically
7. Gossip

### Validation checklist for `POST /block/{fingerprint}/revoke`

1. Fetch the existing block (404 if not found)
2. Check it is not already revoked
3. Verify the revocation signature against the REVOKE payload using the block's own armored key (only the key owner can revoke)
4. Store the revocation and set `revoked = true` atomically
5. Gossip

---

## Step 6: Implement the domain allowlist

Configuration: a list of permitted email domains, plus an `allow_all` boolean.

- If `allow_all` is false and the domain list is empty: reject everything
- If `allow_all` is true: accept any key regardless of UID domains
- Otherwise: accept a key if any of its UIDs contains an email whose domain is in the allowlist

Apply this check to both direct submissions and gossiped blocks.

---

## Step 7: Implement P2P

### Peer registration (`POST /peers`)

1. Parse the `addr` field
2. Reject private/loopback IP addresses (unless configured to allow private peers for testing)
3. Perform a reciprocal reachability check: `GET <addr>/peers` must return 200
4. Add to peer list if not already present and below the cap
5. Register this node with the new peer (`POST <addr>/peers` with this node's address)
6. Initiate background sync with the new peer

### Gossip

On receiving any new block, SigEntry, or revocation (from a client or a peer):

1. Add the event hash to a seen-set (keyed by block hash or sig hash; expire after 1 hour)
2. Select K random peers from the peer list (default K=3)
3. Forward the event to each selected peer via the appropriate `POST /p2p/*` endpoint
4. Do not forward to the peer the event arrived from (use the `from` field in gossip messages)

If a peer returns a non-2xx response, log and continue. Do not retry.

### Sync on connect

After successfully peering with a new node:

1. `GET <peer>/p2p/hashes` → map of `{fingerprint: sig_chain_head}`
2. For each fingerprint in the peer's map that you don't have: `GET <peer>/block/<fingerprint>` and verify before storing
3. For each fingerprint you have that the peer doesn't: `POST <peer>/p2p/block` with the full block
4. For fingerprints both have but with different `sig_chain_head`: fetch the longer chain and verify each SigEntry

Always verify cryptographically before storing. Never trust a peer's data without verification.

### Cross-validation

Periodically (e.g. every 5 minutes) diff your `{fingerprint: sig_chain_head}` map against all peers. Log any discrepancy. A peer with a shorter chain for a key you have is potentially censoring signatures.

---

## Step 8: Point the test suite at your node

```bash
GPGCHAIN_TEST_SERVER=http://localhost:9000 behave tests/
```

All scenarios in `tests/features/` (excluding `@cli`-tagged ones) must pass. Work through failures systematically — each failing scenario tells you exactly which behaviour is missing or wrong.

The feature files are the compliance specification. If a scenario fails and you believe the spec is ambiguous, the scenario clarifies it.

---

## Step 9: Implement the CLI client (optional but recommended)

The CLI client is a separate binary that talks to the node over HTTP. It handles all cryptographic operations that require the private key (signing payloads for `add`, `sign`, `revoke`, `endorse`).

See `docs/cli-reference.md` for the expected behaviour of each command.

To run the CLI test suite against your client, set `GPGCHAIN_CLIENT` to your binary path and run behave with `--tags=@cli`.

---

## Common mistakes

**Wrong payload format** — The signing payloads are typed binary strings, not JSON. `GPGCHAIN_SUBMIT_V1\x00` is the literal ASCII string followed by a null byte, followed by the fingerprint bytes, followed by another null byte, and so on. Make sure you are constructing bytes, not strings.

**Signing the base64 representation** — The `self_sig`, `sig`, etc. fields in requests are base64-encoded. Decode them before passing to your GPG library for verification. The GPG library operates on binary signatures, not base64 strings.

**Wrong fingerprint format** — Fingerprints must be uppercase hex, no spaces, no colons. `A3F9…` not `a3f9…` or `A3:F9…`.

**Mutable blocks** — Block content (fingerprint, armored_key, self_sig) must never change after first write. The block hash is computed from these fields; modifying them invalidates the hash and breaks all downstream verification.

**Sig chain ordering** — When returning a block, the SigEntries in `sig_chain` must be in order from oldest (pointing to the block hash) to newest (pointed to by `sig_chain_head`). Clients follow the chain tip to validate; wrong ordering causes verification failures.

**Domain filter on gossip** — Apply the domain allowlist to gossiped blocks just as you do to direct submissions. A node should never store a block outside its allowlist regardless of where it came from.
