# User Guide

This guide walks through the complete lifecycle of participating in a GPG Chain network: publishing your key, building trust relationships, and finding and verifying keys belonging to others.

For a conceptual introduction see `docs/overview.md`. For full flag documentation see `docs/cli-reference.md`.

---

## Prerequisites

- A GPG Chain node to connect to, or your own node running locally (see `docs/getting-started.md`)
- The `gpgchain` CLI binary on your PATH (built with `./scripts/build.sh`)
- A GPG key pair — you will need both your public and private key files in ASCII-armored format

### Export your keys

```bash
# Export public key
gpg --armor --export alice@example.com > alice.pub.asc

# Export private key
gpg --armor --export-secret-keys alice@example.com > alice.priv.asc
```

Note your fingerprint:

```bash
gpg --fingerprint alice@example.com
```

The fingerprint is the 40-character hex string (without spaces or colons). For example:

```
A3F9 C2E1 B8D4 7650 F29A  3C1E 7B84 D6F5 09E2 8A1C
→ A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
```

Set your environment variables so you don't have to repeat them every command:

```bash
export GPGCHAIN_SERVER=http://keys.example.com
export GPGCHAIN_KEYID=A3F9C2E1B8D47650F29A3C1E7B84D6F509E28A1C
```

---

## Publishing your key

```bash
gpgchain add --key alice.pub.asc --privkey alice.priv.asc
```

This creates a self-signature proving you control the corresponding private key, then posts your key to the node. The node gossips it to its peers automatically.

Verify the submission:

```bash
gpgchain show --fingerprint $GPGCHAIN_KEYID
```

You should see your fingerprint, UIDs, and `Status: active`.

---

## Signing someone else's key

Signing a key means you are vouching for it — asserting that you have personally verified the key belongs to the person it claims to belong to (typically by meeting them in person and checking their fingerprint).

```bash
# Get Bob's fingerprint (from his key or from the ledger)
gpgchain search --email bob@example.com

# Sign Bob's key
gpgchain sign \
    --fingerprint B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F \
    --privkey alice.priv.asc
```

This records a trust signature on Bob's block, cryptographically linked to your fingerprint. Anyone who trusts you can now potentially reach Bob through you in trust graph traversal.

**Only sign keys you have genuinely verified.** Signing is a public, permanent statement of endorsement. It cannot be undone.

---

## Checking whether you trust a key

```bash
gpgchain check --fingerprint B1E72CA4F98053D2E46B71CA3D905F2A1E8B4C7F
```

This evaluates the trust score for Bob's key using your key as the root of trust (from `GPGCHAIN_KEYID`). The default threshold is 1 and the default depth is 2.

Exit code 0 = trusted, exit code 2 = not trusted.

### Adjusting the trust threshold

A threshold of 1 means a single chain of endorsements is sufficient. For higher confidence, require multiple independent paths:

```bash
# Require two independent paths (standard scoring)
gpgchain check --fingerprint <fp> --min-trust 2

# Require two vertex-disjoint paths (stronger — no shared intermediate nodes)
gpgchain check --fingerprint <fp> --min-trust 2 --disjoint
```

See `docs/trust-guide.md` for guidance on choosing the right threshold for your situation.

---

## Listing trusted keys

```bash
# All keys on the node with trust score ≥ 1
gpgchain list --min-trust 1

# Keys with a trust score ≥ 2 (two independent paths)
gpgchain list --min-trust 2

# Show all keys regardless of trust
gpgchain list
```

---

## Finding a key across multiple nodes

If you do not know which node holds a key, use `search`:

```bash
gpgchain search --email carol@example.com
```

The command starts at your configured server and follows `/.well-known/gpgchain.json` links to discover additional nodes that might hold keys for that domain.

You can provide extra seed nodes to broaden the search:

```bash
gpgchain search \
    --email carol@example.com \
    --seeds http://keys.other-org.example,http://backup-node.example
```

---

## Endorsing the keys you trust (bulk signing)

Once you have built up a trust graph, you can use `endorse` to sign all keys that meet your trust threshold in a single operation:

```bash
# Sign all keys with 2+ paths from your root (disjoint scoring)
gpgchain endorse \
    --privkey alice.priv.asc \
    --threshold 2 \
    --disjoint
```

Before doing this for real, use `--dry-run` to see what would be signed:

```bash
gpgchain endorse \
    --threshold 2 \
    --disjoint \
    --dry-run
```

This is particularly useful after a key-signing party: you have verified several keys in person, added their initial direct signatures, and now want to propagate endorsements to keys that are transitively trusted through the people you met.

---

## Revoking your key

If your private key is compromised, revoke it immediately:

```bash
gpgchain revoke --fingerprint $GPGCHAIN_KEYID --privkey alice.priv.asc
```

Revocation is permanent and gossips to all peers. A revoked key becomes a dead end in trust evaluation — no paths flow through it.

If you have multiple nodes, revoke on each one or wait for gossip to propagate (typically within seconds on a well-connected cluster).

---

## Verifying a node's integrity

To check that a node has not tampered with its stored data:

```bash
gpgchain verify
```

This re-verifies every block's hash and every signature. A node that has altered data will fail this check. Run it against multiple nodes to cross-validate:

```bash
gpgchain verify --server http://node-a.example
gpgchain verify --server http://node-b.example
```

If one node fails but others pass, the failing node's data has been tampered with.

---

## Tips

**Sign only what you have verified.** The trust graph is only meaningful if signatures are honest. A signature you give carelessly weakens the entire web of trust for everyone who trusts you.

**Use a high threshold for important decisions.** A threshold of 1 is appropriate for finding keys to encrypt to. A threshold of 2 or 3 with disjoint scoring is more appropriate for high-stakes decisions.

**Cross-check across multiple nodes.** If Alice's block shows different sig chains on different nodes, one of those nodes may be censoring signatures. Use `verify` and compare the output.

**Keep your private key offline.** The `gpgchain` binary reads your private key from a file but never sends it to any server. You can run all signing commands on an air-gapped machine and copy the output manually if needed (though this workflow is not yet built into the CLI).
