# Trust Guide

This guide explains the trust model in practical terms: how to choose depth and threshold, when to use disjoint scoring, and how to reason about what a trust score actually means.

For the formal algorithm specification see `spec/trust.md`.

---

## The fundamental idea

GPG Chain stores cryptographic facts. **Your** `gpgchain` client decides what those facts mean.

The server never tells you whether to trust a key. It hands you the full graph — who has signed whom — and your client evaluates it locally using your own key as the sole anchor.

A trust score is simply a count of how many independent paths lead from your key to the target. More paths = more independent people vouch for the target = harder to fake.

---

## Parameters

Three parameters control trust evaluation. All can be set per command; they have sensible defaults.

### Max depth (default: 2)

How many hops the trust graph traversal will follow. Depth 0 means only your own key. Depth 1 means keys you have directly signed. Depth 2 means keys signed by people you have directly signed.

```
depth 1:  you → alice               (you signed Alice directly)
depth 2:  you → bob → carol         (you signed Bob; Bob signed Carol)
depth 3:  you → bob → carol → dave  (Carol signed Dave)
```

The default of 2 is a reasonable balance. At depth 3 and beyond, you are extending trust to people whose key you have never seen and whose identity you have not personally verified even at second hand. Use depth > 2 only in tightly controlled networks where you have high confidence in all participants.

### Threshold (default: 1)

The minimum score required to consider a key trusted. Score = number of distinct paths from your root to the target within the depth limit.

| Threshold | Meaning |
|---|---|
| 1 | At least one path exists. Someone you transitively trust has vouched for this key. |
| 2 | At least two distinct paths. Two independent people have vouched for this key, via different routes. |
| 3 | At least three distinct paths. Strong independent confirmation. |

The default of 1 is appropriate for everyday use — finding and encrypting to keys you have not personally verified. Raise the threshold when the decision carries real consequences.

### Standard vs disjoint scoring

**Standard scoring** counts all distinct paths (paths that visit different sets of intermediate nodes).

**Disjoint scoring** (`--disjoint`) counts only the maximum number of paths that share no intermediate nodes. This is a stronger measure of independence.

Example: suppose Bob and Charlie both vouch for Alice, and both Bob and Charlie were vouched for by the same person (Dave). With standard scoring, you have two paths to Alice. With disjoint scoring, you still only have one — because both paths pass through Dave.

```
you → dave → bob → alice
you → dave → charlie → alice

Standard score: 2 (two distinct paths)
Disjoint score: 1 (both paths share the intermediate node "dave")
```

Disjoint scoring prevents a single colluding intermediate from generating multiple apparent paths. Use it when Sybil resistance matters.

---

## Choosing settings for common situations

### Casual key discovery

You want to find a key for someone you are going to encrypt email to, and you have a rough idea they are trustworthy via the community.

```
--min-trust 1 --max-depth 2
```

Suitable. One path at depth 2 is enough. You're not making a high-stakes decision.

### Verifying a new business contact

You want to verify that the key you found for a new contact is genuinely theirs before sharing sensitive information.

```
--min-trust 2 --max-depth 2
```

Two independent paths at depth 2. If two unrelated people in your trust network have vouched for this key, it is unlikely to be spoofed.

### High-stakes decisions

You are verifying a key before trusting it with financial, medical, or legal information.

```
--min-trust 2 --max-depth 2 --disjoint
```

Two vertex-disjoint paths at depth 2. No single intermediate colluder can fake two independent endorsements.

### Internal company PKI

You run a tightly controlled corporate node. All participants have been physically verified. You want to endorse all colleagues automatically.

```
# Endorse everyone you can reach at depth 1 (direct chain members)
gpgchain endorse --threshold 1 --max-depth 1 --privkey my.priv.asc

# Or at depth 2 with strong verification requirement
gpgchain endorse --threshold 2 --max-depth 2 --disjoint --privkey my.priv.asc
```

---

## How the scoring algorithm works

The BFS scoring algorithm (`spec/trust.md`) does the following:

1. Build a directed graph: each SigEntry in the ledger becomes an edge `signer → target`.
2. Remove all edges from or to revoked keys.
3. From your root key, perform a BFS counting distinct paths to the target within the depth limit.

A path is counted once per unique set of intermediate nodes it visits. This means if two routes to the same key visit different intermediate people, both count.

With disjoint scoring, the algorithm uses max-flow on a node-split graph (see `spec/trust.md`) to count paths that share no intermediate nodes.

### Your own key always has score 1

The BFS algorithm special-cases `target == root`: it returns 1 immediately. Your own key is always trusted, regardless of whether anyone has signed it. This is by design — you don't need external endorsement for your own key.

### Revoked keys are dead ends

If a key is revoked, no paths pass through it. A revoked signer's endorsements effectively disappear from the trust graph. If the only path to Alice ran through a revoked key, Alice's score drops to 0.

---

## What a trust score does not mean

**A high trust score does not verify identity.** It verifies that a web of GPG signers have all asserted the key belongs to the claimed owner. GPG signatures are easy to create and UIDs are self-asserted. The strength of the assurance depends entirely on the diligence of the people who signed the key.

**Trust is not transitive without limit.** The depth limit exists for a reason. A key five hops away in a large network could belong to anyone; the people who signed it may have applied much weaker verification standards than you would.

**No score cannot be spoofed with enough signers.** An attacker who controls multiple accounts can manufacture paths. Disjoint scoring raises the cost significantly, but the fundamental defence against Sybil attacks is human diligence in the key-signing process — only sign keys you have personally verified.

---

## The `endorse` command and bulk signing

`gpgchain endorse` is a power-user feature for after a key-signing party or internal rollout. It evaluates the trust graph and signs all qualifying keys in one pass.

**Recommended usage pattern:**

1. Hold a key-signing event. Verify fingerprints in person.
2. Add direct signatures for each key you personally verified (`gpgchain sign`).
3. Run `gpgchain endorse --dry-run` to see which additional keys now meet your threshold.
4. Review the dry-run output.
5. If it looks right, run without `--dry-run`.

This pattern lets you extend your endorsements transitively to people in your community you trust at second hand, while keeping full control over which endorsements you actually submit.

**Default threshold of 2:** The `endorse` command defaults to `--threshold 2` rather than 1. This is intentional — endorsing with threshold 1 would sign any key reachable from your root at depth ≤ 2, which may include keys you have only very weakly transitively trusted. The threshold-2 default means a key needs two distinct vouches from within your trust network before you add yours.
