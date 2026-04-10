# Data Model

This document is the canonical definition of the Block and SigEntry data structures, their field semantics, hash computation rules, JSON serialisation requirements, and the Python DirStore file layout.

---

## Block

A Block represents a single GPG public key registered on the ledger. It is identified by its content hash and is immutable once submitted. Trust signatures are appended as a linked chain of SigEntry records anchored to the Block's hash.

| Field | Type | Constraints | Semantics |
|---|---|---|---|
| `hash` | string | 64 uppercase hex chars | SHA-256 of `(fingerprint \|\| 0x00 \|\| armored_key \|\| 0x00 \|\| self_sig)` where all values are the UTF-8 bytes of the field strings and `0x00` is a single null byte separator. Uppercase hex encoding of the digest. This is the block's unique identity and content address. |
| `fingerprint` | string | 40 chars (v4/SHA-1) or 64 chars (v5/SHA-256); uppercase hex; no spaces | The OpenPGP key fingerprint extracted verbatim from the submitted key. |
| `armored_key` | string | Non-empty | Full ASCII-armored OpenPGP public key block, including `-----BEGIN PGP PUBLIC KEY BLOCK-----` header and `-----END PGP PUBLIC KEY BLOCK-----` footer, as produced by `gpg --armor --export`. |
| `uids` | array of strings | At least one entry | UID strings extracted verbatim from the key (e.g. `"Alice Example <alice@example.com>"`). Extracted by the node at submission time. |
| `submit_timestamp` | integer | Unix seconds; positive integer | Chosen and authenticated by the submitting client. Included in the SUBMIT signing payload so the client's signature commits to this value. Nodes must not set or modify this field — they accept whatever value the client embedded in the signed payload. |
| `self_sig` | string | Non-empty; base64-encoded | Base64-encoded detached binary OpenPGP signature over the SUBMIT payload (defined in `payloads.md`). Proves the submitter controls the private key corresponding to the submitted public key. |
| `sig_chain_head` | string | 64 uppercase hex chars, or empty string | Hash of the most recently appended SigEntry. Empty string if no trust signatures have been added yet. Updated atomically each time a new SigEntry is appended. |
| `revoked` | boolean | — | `true` if the key owner has revoked this block. Revocation is permanent; once set to `true` this field never changes back to `false`. |
| `revocation_sig` | string | base64-encoded, or empty string | Base64-encoded detached binary OpenPGP signature over the REVOKE payload. Empty string if `revoked` is `false`. |

### Notes

- `submit_timestamp` is not included in the block hash. It is authenticated indirectly via `self_sig`.
- The block hash is computed from the `self_sig` field value (the base64 string), not from the raw binary signature bytes.
- A block's `hash`, `fingerprint`, `armored_key`, and `self_sig` fields are immutable after submission.
- `uids` is derived by the node at submission time and is also immutable.

---

## SigEntry

A SigEntry records a single trust signature applied to a Block. SigEntries form a per-block singly-linked list: the first entry links to the Block's hash; each subsequent entry links to the hash of the preceding entry. This chain structure makes any tampering (insertion, deletion, reordering) detectable.

| Field | Type | Constraints | Semantics |
|---|---|---|---|
| `hash` | string | 64 uppercase hex chars | SHA-256 of `(prev_hash \|\| 0x00 \|\| signer_fingerprint \|\| 0x00 \|\| sig \|\| 0x00 \|\| str(timestamp))` where all values are UTF-8 bytes and `0x00` is a single null byte separator. Uppercase hex. This is the SigEntry's unique identity. |
| `prev_hash` | string | 64 uppercase hex chars | Hash of the preceding SigEntry in the chain, or the Block's hash if this is the first signature on the block. This field creates the linked chain. |
| `signer_fingerprint` | string | 40 or 64 uppercase hex chars; no spaces | Uppercase hex fingerprint of the signing key. |
| `sig` | string | Non-empty; base64-encoded | Base64-encoded detached binary OpenPGP signature over the TRUST payload (defined in `payloads.md`). |
| `timestamp` | integer | Unix seconds; positive integer | Signing time, chosen and authenticated by the signing client. Included in the TRUST payload so the signer's signature commits to this value. Nodes must not set or modify this field. |
| `signer_armored_key` | string | base64-encoded ASCII-armored key, or empty string | Off-ledger signers only: the signer's full ASCII-armored public key, stored inline in the SigEntry. Empty string for on-ledger signers (those with a block on the local ledger). Stored so that any client can re-verify the signature without fetching the key from another source. |
| `source_node` | string | URL string, or empty string | Off-ledger signers only: the URL of the ledger node where the signer's own block lives. Used by clients for cross-ledger trust traversal. Empty string if not provided or if the signer is on-ledger. |

### Notes

- `signer_armored_key` and `source_node` are populated at submission time and are immutable.
- If a signer is on-ledger (their block exists on the local ledger), `signer_armored_key` must be empty.
- `timestamp` is authenticated via `sig` (it is included in the TRUST payload), so nodes must not override it.

---

## Hash Computation

### Rules

All hashes used in this system follow the same byte-level encoding rules:

1. Each string field is converted to its UTF-8 byte representation before hashing. No BOM, no null terminator.
2. Fields are concatenated with a single null byte (`0x00`, value 0) as separator between consecutive fields.
3. SHA-256 is applied to the resulting byte sequence.
4. The resulting 32-byte digest is encoded as 64 uppercase hexadecimal ASCII characters.
5. There are no length prefixes, no padding, and no other framing.

### Block Hash

**Input fields, in order:** `fingerprint`, `armored_key`, `self_sig`

**Byte sequence:**

```
fingerprint_utf8 + 0x00 + armored_key_utf8 + 0x00 + self_sig_b64_utf8
```

Where:
- `fingerprint_utf8` is the UTF-8 encoding of the uppercase hex fingerprint string (e.g. `"A1B2C3..."`).
- `armored_key_utf8` is the UTF-8 encoding of the full ASCII-armored key string including headers, footers, and all whitespace exactly as stored.
- `self_sig_b64_utf8` is the UTF-8 encoding of the base64-encoded signature string (not the raw binary signature — the base64 string itself).
- `0x00` is one null byte separating each field.

**Result:** SHA-256 of the above byte sequence, encoded as 64 uppercase hex characters.

### SigEntry Hash

**Input fields, in order:** `prev_hash`, `signer_fingerprint`, `sig`, `timestamp`

**Byte sequence:**

```
prev_hash_utf8 + 0x00 + signer_fingerprint_utf8 + 0x00 + sig_b64_utf8 + 0x00 + decimal_timestamp_utf8
```

Where:
- `prev_hash_utf8` is the UTF-8 encoding of the uppercase hex prev_hash string.
- `signer_fingerprint_utf8` is the UTF-8 encoding of the uppercase hex fingerprint string.
- `sig_b64_utf8` is the UTF-8 encoding of the base64-encoded sig string.
- `decimal_timestamp_utf8` is the UTF-8 encoding of the timestamp as a decimal integer string with no leading zeros (e.g. `"1712345678"`).

**Result:** SHA-256 of the above byte sequence, encoded as 64 uppercase hex characters.

---

## Sig Chain Invariants

The SigEntry linked list attached to each Block must satisfy all of the following invariants at all times:

1. **First entry links to block:** The `prev_hash` of the first SigEntry in the chain equals the Block's `hash`.
2. **Subsequent entries link to predecessor:** For every SigEntry except the first, its `prev_hash` equals the `hash` of the immediately preceding SigEntry.
3. **Head pointer is current:** The Block's `sig_chain_head` always equals the `hash` of the most recently appended SigEntry. If no SigEntries exist, `sig_chain_head` is the empty string.
4. **Chain terminates at block hash:** Following `prev_hash` links from `sig_chain_head` must eventually reach the Block's `hash`, with no gaps or cycles.
5. **Hash integrity:** Every SigEntry's `hash` field must equal the SHA-256 computed from its own fields per the rules above.

**Tampering detection:** Any SigEntry whose computed hash does not match its stored `hash` field, or whose `prev_hash` does not match the preceding entry's `hash`, indicates that the chain has been tampered with.

**Chain verification procedure:** Starting from `sig_chain_head`, retrieve each SigEntry, verify its `hash` against its fields, then follow `prev_hash`. The chain is valid when this traversal terminates at the Block's `hash`. The number of traversal steps equals the number of SigEntries in the chain.

---

## JSON Serialisation

When serialised to JSON (for storage and HTTP responses):

- All field names are `snake_case` as defined in the field tables above.
- **All fields must be present** in the serialised form even if their value is empty, zero, or false. Use:
  - Empty string `""` for string fields with no value.
  - `false` for boolean fields that are not set.
  - `0` for integer fields that are zero (though `submit_timestamp` and `timestamp` should never be zero in practice).
  - `[]` for empty arrays.
- **Exception:** `signer_armored_key` and `source_node` on SigEntry **may be omitted entirely** from JSON serialisation when they are empty strings. They are optional off-ledger fields and clients must handle their absence. When present, they must be non-empty strings.
- `submit_timestamp` and `timestamp` are JSON integers (not strings). They must not be quoted.
- `revoked` is a JSON boolean (`true` or `false`). It must not be a string.
- `uids` is a JSON array of strings.

### Block JSON Example Structure

```json
{
  "hash": "A1B2C3D4...",
  "fingerprint": "ABCDEF1234567890ABCDEF1234567890ABCDEF12",
  "armored_key": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n...\n-----END PGP PUBLIC KEY BLOCK-----\n",
  "uids": ["Alice Example <alice@example.com>"],
  "submit_timestamp": 1712345678,
  "self_sig": "iQEzBAABCAAdFiEE...",
  "sig_chain_head": "F1E2D3C4...",
  "revoked": false,
  "revocation_sig": ""
}
```

### SigEntry JSON Example Structure (on-ledger signer)

```json
{
  "hash": "1A2B3C4D...",
  "prev_hash": "A1B2C3D4...",
  "signer_fingerprint": "FEDCBA0987654321FEDCBA0987654321FEDCBA09",
  "sig": "iQEzBAABCAAdFiEE...",
  "timestamp": 1712350000
}
```

### SigEntry JSON Example Structure (off-ledger signer)

```json
{
  "hash": "1A2B3C4D...",
  "prev_hash": "A1B2C3D4...",
  "signer_fingerprint": "FEDCBA0987654321FEDCBA0987654321FEDCBA09",
  "sig": "iQEzBAABCAAdFiEE...",
  "timestamp": 1712350000,
  "signer_armored_key": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n...\n-----END PGP PUBLIC KEY BLOCK-----\n",
  "source_node": "https://keys.partner.org"
}
```

---

## Python DirStore File Layout

The Python reference implementation uses a directory tree of immutable JSON files as its backing store. Disk is the source of truth; no in-memory ledger is maintained between requests.

### Directory Structure

```
<store_dir>/
  <level1>/
    <level2>/
      <fingerprint>.block.json
      <fingerprint>.sig.<sig_hash>.json
      <fingerprint>.sig.<sig_hash2>.json
      ...
      <fingerprint>.revoke.json
```

### Path Derivation

Given a fingerprint `FP` and the default prefix length N=4 (split 2+2):

```
level1 = FP[0:2]   (first two uppercase hex characters)
level2 = FP[2:4]   (next two uppercase hex characters)
```

All three file types for a given key live in the same directory: `<store_dir>/<level1>/<level2>/`.

### File Types

| Suffix | Contents | Written | Mutable? |
|---|---|---|---|
| `<FP>.block.json` | Full Block object (all fields except `sig_chain_head`, which is maintained separately) | Once at submission | No |
| `<FP>.sig.<sig_hash>.json` | Single SigEntry object | Once when the SigEntry is appended | No |
| `<FP>.revoke.json` | JSON object with `revocation_sig` (string) and `revoked_at` (integer unix timestamp, informational) | Once at revocation | No |

Where `<sig_hash>` is the 64-character uppercase hex hash of the SigEntry.

### Atomic Writes

All file writes are performed atomically to avoid partial writes being visible to concurrent readers:

1. Write the full content to `<target_path>.tmp`.
2. `rename()` (or `os.replace()`) the `.tmp` file to `<target_path>`.

This relies on POSIX rename atomicity. The `.tmp` suffix must not be used for any permanent file.

### Read and Reconstruction

To load a Block for a given fingerprint:

1. Compute the directory path from the fingerprint.
2. Read `<FP>.block.json` — this provides all immutable fields.
3. Enumerate all files matching `<FP>.sig.*.json` in the same directory. Load each as a SigEntry.
4. Reconstruct the sig chain by following `prev_hash` links, starting from the Block's `hash` and following forward. The final SigEntry (the one not referenced as `prev_hash` by any other) is the chain head; set `sig_chain_head` accordingly.
5. If `<FP>.revoke.json` exists, set `revoked = true` and load the `revocation_sig`.
6. Place the assembled Block in the LRU cache.

The LRU cache holds fully assembled Block objects (default capacity 128). On a cache hit, disk is not consulted.

### Enumeration

`GET /blocks` and `GET /search?q=` require enumerating all blocks. The implementation walks the directory tree, loads each `*.block.json` file (consulting the LRU cache first), and assembles the result. The walk populates the cache as it proceeds.

### Startup

The node verifies the store directory exists and is writable, then begins serving immediately. No pre-scan, no pre-loading, no index file.
