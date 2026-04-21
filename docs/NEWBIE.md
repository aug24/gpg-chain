# Why blockchain? A beginner's guide

## The problem we're solving

Imagine you receive an encrypted email from someone claiming to be your bank. To read it you need their public encryption key. But how do you know the key actually belongs to your bank, and not to an attacker who is pretending to be them?

This is the **key distribution problem**, and it is one of the oldest unsolved problems in practical cryptography. GPG Chain is an attempt to solve it using ideas borrowed from blockchain design.

---

## What is a blockchain, really?

Strip away the cryptocurrency hype and a blockchain is just a very specific way of writing down a list of facts so that nobody can secretly change what was written earlier.

The trick is **cryptographic hashing**. A hash function takes any piece of data and produces a short fixed-length fingerprint — a string of letters and numbers that looks like gibberish. The same input always produces exactly the same fingerprint. Change even one character of the input and the fingerprint changes completely and unpredictably.

A **block** is a bundle of data (in Bitcoin: a batch of transactions; here: a GPG public key) plus the hash of the previous block. Linking each new block to the hash of the one before it creates a **chain**:

```
Block 1            Block 2                 Block 3
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ data        │    │ data             │    │ data             │
│ hash: A1B2… │◄───│ prev_hash: A1B2… │◄───│ prev_hash: C3D4… │
└─────────────┘    │ hash: C3D4…      │    │ hash: E5F6…      │
                   └──────────────────┘    └──────────────────┘
```

If someone goes back and quietly changes Block 1 — to alter a fact that was recorded there — its hash changes. That breaks Block 2's `prev_hash` field, which changes Block 2's hash, which breaks Block 3, and so on all the way to the present. **The entire chain after the tampered block becomes detectably invalid.** You cannot rewrite history without everyone noticing.

That is the core insight of blockchain: **the structure makes tampering visible**.

---

## What GPG Chain stores

Each entry in this ledger is a GPG public key. When you publish your key, the ledger records:

- Your **armored public key** (the actual cryptographic material)
- A **self-signature** — a cryptographic proof that whoever submitted this key holds the corresponding private key
- A **content hash** that permanently and uniquely identifies this entry

That content hash is the block's identity. It is computed from the key material and self-signature, so two different keys will always have different hashes. Nobody can replace your key with someone else's without producing a completely different hash — which every copy of the ledger would immediately disagree with.

---

## The signature chain

On top of the basic block structure, GPG Chain adds a second linked chain *inside* each block: the **signature chain**.

When Alice decides she trusts Bob's key — perhaps because she met him in person and verified his fingerprint — she signs a short payload that records:

- Bob's block hash (which block she is vouching for)
- Her own fingerprint (who is doing the vouching)
- A timestamp

That signature becomes a **SigEntry**, and it points back to the previous SigEntry (or to the block itself if this is the first signature):

```
Bob's block hash: C3D4…
       │
       ▼
SigEntry 1: Alice vouches for Bob   hash: X1Y2…
       │
       ▼
SigEntry 2: Carol vouches for Bob   hash: Z3W4…
       │
       ▼
SigEntry 3: Dave vouches for Bob    hash: Q5R6…
```

Each entry's hash covers the previous entry's hash, so the chain is tamper-evident in the same way as the block chain itself. A node that quietly removes Carol's vouching or reorders the entries will produce a chain that any other node can detect as broken.

---

## Why distribute it across many nodes?

A single server holding all the keys would be a single point of failure and a single point of trust: you would simply have to believe whatever that server told you. That is not much better than asking your bank to hand you their own encryption key and hoping they are honest.

GPG Chain spreads the ledger across many independent nodes. Each node holds a copy. When a new key or signature arrives, nodes gossip it to their peers, so eventually every node has the same data.

This matters for two reasons:

**Censorship resistance.** A malicious node cannot simply hide a key or a signature. Any client can ask multiple nodes and cross-check the answers. If node A claims Bob's block has only two signatures but node B shows three, something is wrong with node A.

**Tamper detection.** Because blocks are identified by their content hash, and because the signature chain is cryptographically linked, a node cannot silently alter stored data. Any modification produces a detectable hash mismatch that any other node can spot.

---

## Why is this a good fit for key distribution?

Put the pieces together:

| Property | Why it matters for key distribution |
|---|---|
| **Content-addressed blocks** | A key's identity is its hash. There is no "version 2" of a key — a different key is a different block. |
| **Self-signatures required** | You cannot publish someone else's key on their behalf. Submission requires proving you hold the private key. |
| **Linked signature chain** | The record of who has endorsed whom cannot be quietly edited. Trust history is permanent and verifiable. |
| **Distributed** | No single party controls the ledger. You can cross-check any node against others. |
| **Client-side trust** | The network stores cryptographic facts. *You* decide what those facts mean. Whether a chain of endorsements is sufficient to trust a key is your decision, evaluated locally with your own root of trust. |

The result is a system where:

1. If you find a key for `alice@example.com`, you can verify the key material has not been tampered with (hash check).
2. You can verify Alice herself published it (self-signature check).
3. You can see whether people you already trust have vouched for it (signature chain traversal).
4. You can cross-check your answer across multiple independent nodes (distributed replication).
5. No single node — not even the one that first accepted Alice's key — can retroactively alter or erase any of the above.

---

## Signing as proof-of-work

Bitcoin's proof-of-work asks miners to burn CPU cycles until they find a hash that meets an arbitrary difficulty target. The point is not the burning itself — it is that producing a valid result requires real, verifiable effort that nobody can fake.

GPG signing is proof-of-work in exactly this sense. It is easy for the person who holds the private key: a fraction of a second on any modern computer. But for everyone else — anyone trying to forge that signature without the key — it is computationally infeasible. Breaking Ed25519 or RSA-2048 would require more computation than exists on Earth. The hardness of forgery is just as real and absolute as the hardness of Bitcoin mining; it is simply concentrated at the cryptographic boundary rather than spread across repeated hashing.

The fact that signing feels effortless to the legitimate holder does not weaken this guarantee at all. What matters is that a forger cannot do it at any cost.

There is a second layer of work on top of the cryptographic one: accumulating endorsements. Creating a thousand GPG keys takes seconds. Getting real people to sign them does not — a signature is a claim that the signer has personally verified the key owner's identity. You cannot automate or compute your way to a web of genuine endorsements; you have to earn them. This social cost is an additional barrier, built on top of the cryptographic one.

The important difference from Bitcoin's PoW is that here signing does not drive **consensus**. In Bitcoin, the chain with the most accumulated computational work wins, and this resolves disputes about which version of history is correct. GPG Chain has no such race. Validity is purely cryptographic — a block is valid if the signatures check out and the hash chain is intact — and two nodes can permanently hold different subsets of keys without that being a problem.

So: signatures are GPG Chain's proof-of-work for *identity*, while cryptographic hashing provides immutability. The competitive consensus mechanism that PoW adds in Bitcoin is simply not needed here, because there is no shared financial state to agree on.

---

## What this is not

It is worth being clear about what is missing compared to a currency blockchain like Bitcoin:

- **No competitive consensus.** There is no mining race, no "longest chain wins" rule, no need to outpace other participants. Nodes converge on the same data by gossiping and cross-checking, not by competition.
- **No total ordering.** Blocks are not numbered. Two nodes can have different subsets of keys; that is fine. Valid state is the *union* of all independently verifiable blocks.
- **No tokens or financial incentives.** There is nothing to mine or spend. Nodes participate because they want reliable key distribution, not for profit.

This makes GPG Chain much simpler than a currency blockchain, and that simplicity is a feature: there are fewer moving parts that can go wrong, and the security properties are easier to reason about.
