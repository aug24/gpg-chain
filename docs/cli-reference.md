# CLI Reference

The `gpgchain` binary is the Go implementation's command-line client. It communicates with a running GPG Chain node over HTTP and handles all cryptographic operations locally.

```
gpgchain <command> [flags]
```

---

## Global conventions

**Server flag:** Every command accepts `--server <url>`. If omitted, the value of `GPGCHAIN_SERVER` is used. If that is also unset, the command fails with an error.

**Key identity flag:** Commands that evaluate trust or sign on your behalf accept `--keyid <fingerprint>`. If omitted, the value of `GPGCHAIN_KEYID` is used.

**Private key flag:** Commands that sign payloads accept `--privkey <path>` pointing to an ASCII-armored private key file. The file is read once and its contents are never written to disk or sent to the server.

**Fingerprint format:** Uppercase hex, no spaces (e.g. `A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C`).

**Exit codes:** 0 = success, 1 = error (network, invalid input, verification failure), 2 = not found or not trusted (for `check`).

---

## add

Submit a GPG public key to the ledger.

```
gpgchain add --key <path> --privkey <path> [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--key` | yes | Path to ASCII-armored public key file |
| `--privkey` | yes | Path to ASCII-armored private key file (used to create the self-signature) |
| `--server` | yes* | Node URL. Falls back to `GPGCHAIN_SERVER`. |

The command:
1. Reads the public key and extracts the fingerprint
2. Creates a SUBMIT payload and signs it with the private key
3. Posts the key and self-signature to `POST /block`
4. On success, prints the block hash and fingerprint

**Example:**
```bash
gpgchain add \
    --server http://localhost:8080 \
    --key alice.pub.asc \
    --privkey alice.priv.asc
```

**Output:**
```
Added block A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
Hash: F1E2D3C4B5A697886950...
```

**Exit codes:** 0 = success, 1 = error (network, invalid key, self-sig rejected)

---

## show

Display a single block from the ledger.

```
gpgchain show --fingerprint <fp> [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--fingerprint` | yes | Fingerprint of the key to display |
| `--server` | yes* | Node URL |

Prints the block hash, fingerprint, UIDs, submit timestamp, revocation status, and the full signature chain (each signer's fingerprint and timestamp).

**Example:**
```bash
gpgchain show \
    --server http://localhost:8080 \
    --fingerprint A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
```

**Output:**
```
Fingerprint: A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
Status:      active
UIDs:        alice@example.com
Hash:        F1E2D3C4B5A697886950...
Submitted:   2026-04-22 10:00:00 UTC

Signatures (2):
  B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F  2026-04-22 11:00:00 UTC
  C3D4E5F67890AB12CD34EF5678901234ABCDEF56  2026-04-22 12:00:00 UTC
```

**Exit codes:** 0 = success, 1 = not found or network error

---

## sign

Append a trust signature to a block.

```
gpgchain sign --fingerprint <fp> --keyid <your-fp> --privkey <path> [--server <url>] [--signer-key <path>] [--source-node <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--fingerprint` | yes | Fingerprint of the key to sign |
| `--keyid` | yes* | Your fingerprint. Falls back to `GPGCHAIN_KEYID`. |
| `--privkey` | yes | Path to your ASCII-armored private key file |
| `--server` | yes* | Node URL |
| `--signer-key` | no | Path to your armored public key, for off-ledger signing |
| `--source-node` | no | URL of the ledger where your key lives, for off-ledger signing |

The command:
1. Fetches the target block to get its hash
2. Creates a TRUST payload and signs it with your private key
3. Posts the signature to `POST /block/{fingerprint}/sign`

For off-ledger signing (when your key is not on the target node): provide `--signer-key` with your armored public key. The node verifies and stores it inline. Optionally provide `--source-node` to enable cross-ledger trust traversal by clients.

**Example:**
```bash
gpgchain sign \
    --server http://localhost:8080 \
    --fingerprint A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --privkey bob.priv.asc
```

**Output:**
```
Signed block A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
SigEntry hash: 9A8B7C6D5E4F3A2B1C0D...
```

**Exit codes:** 0 = success, 1 = error

---

## revoke

Revoke your key. Only the key owner (holder of the private key) can revoke.

```
gpgchain revoke --fingerprint <fp> --privkey <path> [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--fingerprint` | yes | Fingerprint of the key to revoke |
| `--privkey` | yes | Path to your ASCII-armored private key file |
| `--server` | yes* | Node URL |

Revocation is permanent. The block remains on the ledger (for audit purposes) but is marked `revoked=true` and contributes no paths in trust evaluation.

**Example:**
```bash
gpgchain revoke \
    --server http://localhost:8080 \
    --fingerprint A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C \
    --privkey alice.priv.asc
```

**Output:**
```
Revoked A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
```

**Exit codes:** 0 = success, 1 = error (already revoked, key not found, sig rejected)

---

## list

List keys on the ledger, optionally filtered by trust score.

```
gpgchain list [--keyid <fp>] [--min-trust <n>] [--max-depth <n>] [--disjoint] [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--keyid` | no | Your fingerprint (root of trust). Required if `--min-trust` > 0. Falls back to `GPGCHAIN_KEYID`. |
| `--min-trust` | no | Minimum trust score to include (default 0 = show all) |
| `--max-depth` | no | Maximum path depth for trust evaluation (default 2) |
| `--disjoint` | no | Use vertex-disjoint scoring instead of standard path counting |
| `--server` | yes* | Node URL |

Without `--min-trust`, lists all blocks with their fingerprints and UIDs. With `--min-trust N`, fetches all blocks, builds the trust graph, and shows only keys with score ≥ N from `--keyid`.

**Example — list all keys:**
```bash
gpgchain list --server http://localhost:8080
```

**Example — list trusted keys (standard scoring):**
```bash
gpgchain list \
    --server http://localhost:8080 \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --min-trust 1
```

**Example — list with strong (disjoint) trust filter:**
```bash
gpgchain list \
    --server http://localhost:8080 \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --min-trust 2 \
    --disjoint
```

**Output:**
```
A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com  (trust=2)
C3D4E5F67890AB12CD34EF5678901234ABCDEF56  carol@example.com  (trust=1)
```

**Exit codes:** 0 = success, 1 = error

---

## check

Evaluate the trust score for a specific key.

```
gpgchain check --fingerprint <fp> --keyid <fp> [--min-trust <n>] [--max-depth <n>] [--disjoint] [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--fingerprint` | yes | Fingerprint of the key to evaluate |
| `--keyid` | yes* | Your fingerprint (root of trust). Falls back to `GPGCHAIN_KEYID`. |
| `--min-trust` | no | Trust threshold (default 1) |
| `--max-depth` | no | Maximum path depth (default 2) |
| `--disjoint` | no | Use vertex-disjoint scoring |
| `--server` | yes* | Node URL |

Prints the trust score and a TRUSTED / NOT TRUSTED verdict.

**Example:**
```bash
gpgchain check \
    --server http://localhost:8080 \
    --fingerprint A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F
```

**Output (trusted):**
```
A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com
Trust score: 2
TRUSTED (threshold: 1)
```

**Output (not trusted):**
```
A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com
Trust score: 0
NOT TRUSTED (threshold: 1)
```

**Exit codes:** 0 = trusted, 1 = block not found, 2 = not trusted

---

## search

Search for keys by email address.

```
gpgchain search --email <addr> [--server <url>] [--seeds <url,...>]
```

| Flag | Required | Description |
|---|---|---|
| `--email` | yes | Email address to search for |
| `--server` | yes* | Starting node URL |
| `--seeds` | no | Additional seed node URLs (comma-separated) |

Performs a cross-ledger BFS starting from the given node(s), using `/.well-known/gpgchain.json` to discover additional nodes that accept the target domain. Returns all blocks whose UIDs match the email address.

**Example:**
```bash
gpgchain search \
    --server http://localhost:8080 \
    --email alice@example.com
```

**Output:**
```
A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com
  node: http://localhost:8080
  sigs: 3
```

**Exit codes:** 0 = success (including no results), 1 = network error

---

## verify

Verify the cryptographic integrity of all blocks on a node.

```
gpgchain verify [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--server` | yes* | Node URL |

For each block:
- Recomputes the block hash and checks it matches the stored hash
- Verifies the self-signature against the SUBMIT payload
- Traverses the sig chain, verifying each SigEntry's hash and signature
- Reports any verification failure

If all blocks pass: prints a summary and exits 0.
If any block fails: prints the specific failures and exits 1.

**Example:**
```bash
gpgchain verify --server http://localhost:8080
```

**Output (success):**
```
Verified 4 blocks
  A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com  OK (2 sigs)
  B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F  bob@example.com    OK (0 sigs)
  C3D4E5F67890AB12CD34EF5678901234ABCDEF56  carol@example.com  OK (1 sig)
  D5E6F7890123ABCD4567EF890123456789ABCDEF  dave@example.com   OK (0 sigs)
verified OK
```

**Exit codes:** 0 = all blocks verified, 1 = one or more failures

---

## endorse

Sign all keys that meet your trust threshold and have not already been signed by you.

```
gpgchain endorse --keyid <fp> --privkey <path> [--threshold <n>] [--max-depth <n>] [--disjoint] [--dry-run] [--server <url>]
```

| Flag | Required | Description |
|---|---|---|
| `--keyid` | yes* | Your fingerprint (root of trust). Falls back to `GPGCHAIN_KEYID`. |
| `--privkey` | no | Path to your armored private key. Required unless `--dry-run`. |
| `--threshold` | no | Minimum trust score to endorse (default 2) |
| `--max-depth` | no | Maximum path depth for trust evaluation (default 2) |
| `--disjoint` | no | Use vertex-disjoint scoring |
| `--dry-run` | no | Show what would be signed without signing anything |
| `--server` | yes* | Node URL |

The command:
1. Fetches all blocks from the node
2. Builds the trust graph
3. For each non-self, non-revoked block: computes the trust score
4. Skips blocks already signed by you
5. Signs all blocks with score ≥ threshold (unless `--dry-run`)
6. Reports the results

The default threshold of 2 means a key must have at least two independent paths from your root before you add your endorsement. This prevents inadvertently endorsing keys you have not adequately verified.

**Example — endorse with standard scoring:**
```bash
gpgchain endorse \
    --server http://localhost:8080 \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --privkey bob.priv.asc
```

**Example — endorse with strong (disjoint) trust requirement:**
```bash
gpgchain endorse \
    --server http://localhost:8080 \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --privkey bob.priv.asc \
    --threshold 2 \
    --disjoint
```

**Example — dry run:**
```bash
gpgchain endorse \
    --server http://localhost:8080 \
    --keyid B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --dry-run \
    --threshold 1
```

**Output (live):**
```
signed: A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com (trust=2)
already signed: C3D4E5F67890AB12CD34EF5678901234ABCDEF56  carol@example.com
3 below threshold (score < 2)
1 signed, 1 already signed, 3 below threshold
```

**Output (dry run):**
```
would sign: A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C  alice@example.com (trust=2)
1 would be signed, 1 already signed, 3 below threshold
```

**Exit codes:** 0 = success, 1 = error

---

## Environment variables

| Variable | Equivalent flag | Notes |
|---|---|---|
| `GPGCHAIN_SERVER` | `--server` | Default node URL |
| `GPGCHAIN_KEYID` | `--keyid` | Your key fingerprint |

Flags always take precedence over environment variables.
