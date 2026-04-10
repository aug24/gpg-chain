# Signing Payloads

This document defines the exact binary byte sequences that clients must construct and sign when submitting a key, adding a trust signature, or revoking a block. These payloads are the canonical signed material — implementations must produce and verify them exactly.

---

## Format Rules

- All payloads are **byte strings**, not text strings. They are constructed as sequences of bytes and passed directly to GPG for signing/verification.
- The domain prefix (`GPGCHAIN_SUBMIT_V1`, etc.) is ASCII-encoded, no null terminator at its end.
- Fields are separated by a single null byte (`0x00`, integer value 0). There are no spaces, no newlines, no other separators.
- All fingerprints are uppercase hexadecimal ASCII (e.g. `ABCDEF1234567890ABCDEF1234567890ABCDEF12`).
- All hash values are uppercase hexadecimal ASCII (e.g. `A1B2C3D4E5F6...`).
- Timestamps are decimal ASCII digits with no leading zeros (e.g. `1712345678`). They represent Unix seconds.
- The SHA-256 hash used in the SUBMIT payload is computed over the UTF-8 bytes of the `armored_key` string field (the ASCII-armored key exactly as stored), encoded as 64 uppercase hex ASCII characters.
- Signatures produced by GPG over these payloads are detached binary signatures (not ASCII-armored). They are stored in the data model base64-encoded.
- Domain separation: no two payload types share the same prefix, so a signature over one type can never be mistaken for a signature over another.

---

## GPGCHAIN_SUBMIT_V1

### Purpose

Proves that the entity submitting a key to the ledger controls the corresponding private key. Also commits to the submission timestamp and a hash of the armored key content, preventing any modification of the stored key.

### Byte Sequence

```
GPGCHAIN_SUBMIT_V1 0x00 <fingerprint> 0x00 <sha256_of_armored_key> 0x00 <timestamp>
```

Expanded:

```
[ASCII bytes of "GPGCHAIN_SUBMIT_V1"] [0x00] [ASCII bytes of uppercase hex fingerprint] [0x00] [ASCII bytes of uppercase hex SHA-256 of armored_key] [0x00] [ASCII bytes of decimal timestamp]
```

### Fields

| Field | Value | Encoding |
|---|---|---|
| Domain prefix | `GPGCHAIN_SUBMIT_V1` | 18 ASCII bytes |
| Separator | — | 1 null byte |
| `fingerprint` | Uppercase hex fingerprint of the submitted key | 40 ASCII bytes (v4) or 64 ASCII bytes (v5) |
| Separator | — | 1 null byte |
| `sha256_of_armored_key` | SHA-256 of the UTF-8 bytes of the `armored_key` field, uppercase hex | 64 ASCII bytes |
| Separator | — | 1 null byte |
| `timestamp` | Decimal representation of the Unix timestamp | Variable-length ASCII digits |

### What Is Signed

This payload is signed by the **private key corresponding to the submitted public key**. The node verifies the signature using the submitted public key itself.

### Binding Properties

- Binds the submission to a specific key (via fingerprint).
- Binds the submission to a specific key content (via SHA-256 of armored key) — prevents the node from swapping the key bytes.
- Binds the submission to a specific timestamp — the timestamp in the Block's `submit_timestamp` field must match.

---

## GPGCHAIN_TRUST_V1

### Purpose

Expresses "I vouch for the key identified by block hash `<block_hash>`, and I sign this at timestamp `<timestamp>`." Links the trust assertion to the specific content of the target block via the block hash.

### Byte Sequence

```
GPGCHAIN_TRUST_V1 0x00 <block_hash> 0x00 <signer_fingerprint> 0x00 <timestamp>
```

Expanded:

```
[ASCII bytes of "GPGCHAIN_TRUST_V1"] [0x00] [ASCII bytes of uppercase hex block hash] [0x00] [ASCII bytes of uppercase hex signer fingerprint] [0x00] [ASCII bytes of decimal timestamp]
```

### Fields

| Field | Value | Encoding |
|---|---|---|
| Domain prefix | `GPGCHAIN_TRUST_V1` | 17 ASCII bytes |
| Separator | — | 1 null byte |
| `block_hash` | Uppercase hex hash of the target Block | 64 ASCII bytes |
| Separator | — | 1 null byte |
| `signer_fingerprint` | Uppercase hex fingerprint of the signing key | 40 or 64 ASCII bytes |
| Separator | — | 1 null byte |
| `timestamp` | Decimal representation of the Unix timestamp | Variable-length ASCII digits |

### What Is Signed

This payload is signed by the **signer's private key**. The node verifies the signature using either the signer's on-ledger armored key or the `signer_armored_key` field supplied with the request (for off-ledger signers).

### Binding Properties

- Binds the trust assertion to a specific target block by content hash.
- Binds the assertion to the specific signer by fingerprint — a signature cannot be attributed to a different key.
- Binds to a timestamp — the timestamp in the SigEntry's `timestamp` field must match.

---

## GPGCHAIN_REVOKE_V1

### Purpose

Proves the key owner intends to permanently revoke their block from the ledger. No timestamp is included — revocation time is informational only and has no security significance. The signature binds to both the fingerprint and the block hash, ensuring it applies to exactly one block.

### Byte Sequence

```
GPGCHAIN_REVOKE_V1 0x00 <fingerprint> 0x00 <block_hash>
```

Expanded:

```
[ASCII bytes of "GPGCHAIN_REVOKE_V1"] [0x00] [ASCII bytes of uppercase hex fingerprint] [0x00] [ASCII bytes of uppercase hex block hash]
```

### Fields

| Field | Value | Encoding |
|---|---|---|
| Domain prefix | `GPGCHAIN_REVOKE_V1` | 18 ASCII bytes |
| Separator | — | 1 null byte |
| `fingerprint` | Uppercase hex fingerprint of the key being revoked | 40 or 64 ASCII bytes |
| Separator | — | 1 null byte |
| `block_hash` | Uppercase hex hash of the Block being revoked | 64 ASCII bytes |

### What Is Signed

This payload is signed by the **private key corresponding to the block being revoked** (i.e. the key identified by `fingerprint`). The node verifies the signature using the public key stored in the block's `armored_key` field.

### Binding Properties

- Binds the revocation to a specific key (fingerprint) — another key owner cannot revoke someone else's block.
- Binds the revocation to specific block content (block hash) — a revocation signature cannot be replayed against a different version of the same key.

---

## Worked Examples

The following examples use a fictional 40-character v4 fingerprint, fictional SHA-256 hashes, and a plausible Unix timestamp. All values are consistent with the rules above.

### Input Values (shared)

```
fingerprint         = "A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C"
sha256_of_armored   = "7E4A1F9C2B835D604E7CF8A31B92D0FE5A47C863D19F04B72E58A3C1906BDF74"
block_hash          = "D84C2F1E9A305B76C4E8F92A03B17D5E684C29A1F0378BE45CD91A37260F8B4E"
signer_fingerprint  = "B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F"
timestamp           = 1712345678
```

---

### Example 1: GPGCHAIN_SUBMIT_V1

**Input values:**
- `fingerprint` = `A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C`
- `sha256_of_armored_key` = `7E4A1F9C2B835D604E7CF8A31B92D0FE5A47C863D19F04B72E58A3C1906BDF74`
- `timestamp` = `1712345678`

**Byte sequence (null bytes shown as `\x00`):**

```
GPGCHAIN_SUBMIT_V1\x00A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C\x007E4A1F9C2B835D604E7CF8A31B92D0FE5A47C863D19F04B72E58A3C1906BDF74\x001712345678
```

**Length calculation:**

| Segment | Length (bytes) |
|---|---|
| `GPGCHAIN_SUBMIT_V1` | 18 |
| `\x00` | 1 |
| fingerprint (40 chars) | 40 |
| `\x00` | 1 |
| sha256_of_armored_key (64 chars) | 64 |
| `\x00` | 1 |
| `1712345678` (10 chars) | 10 |
| **Total** | **135** |

---

### Example 2: GPGCHAIN_TRUST_V1

**Input values:**
- `block_hash` = `D84C2F1E9A305B76C4E8F92A03B17D5E684C29A1F0378BE45CD91A37260F8B4E`
- `signer_fingerprint` = `B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F`
- `timestamp` = `1712345678`

**Byte sequence (null bytes shown as `\x00`):**

```
GPGCHAIN_TRUST_V1\x00D84C2F1E9A305B76C4E8F92A03B17D5E684C29A1F0378BE45CD91A37260F8B4E\x00B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F\x001712345678
```

**Length calculation:**

| Segment | Length (bytes) |
|---|---|
| `GPGCHAIN_TRUST_V1` | 17 |
| `\x00` | 1 |
| block_hash (64 chars) | 64 |
| `\x00` | 1 |
| signer_fingerprint (40 chars) | 40 |
| `\x00` | 1 |
| `1712345678` (10 chars) | 10 |
| **Total** | **134** |

---

### Example 3: GPGCHAIN_REVOKE_V1

**Input values:**
- `fingerprint` = `A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C`
- `block_hash` = `D84C2F1E9A305B76C4E8F92A03B17D5E684C29A1F0378BE45CD91A37260F8B4E`

**Byte sequence (null bytes shown as `\x00`):**

```
GPGCHAIN_REVOKE_V1\x00A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C\x00D84C2F1E9A305B76C4E8F92A03B17D5E684C29A1F0378BE45CD91A37260F8B4E
```

**Length calculation:**

| Segment | Length (bytes) |
|---|---|
| `GPGCHAIN_REVOKE_V1` | 18 |
| `\x00` | 1 |
| fingerprint (40 chars) | 40 |
| `\x00` | 1 |
| block_hash (64 chars) | 64 |
| **Total** | **124** |
