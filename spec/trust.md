# Trust Algorithm

This document defines the complete client-side trust evaluation algorithm, including graph construction, BFS-based path scoring, cycle detection, depth limiting, revoked-node handling, off-ledger signer resolution, and cross-ledger traversal.

---

## Principles

- **Trust decisions are always made by the client.** The server is a store and retrieval mechanism for cryptographic material. It never evaluates, scores, filters, or expresses an opinion on trust. Any computation described in this document is implemented in the client, not the server.
- **The client's own key is the sole root of trust.** It is never derived from or influenced by the network. A client that does not know its own key identity cannot evaluate trust.
- **The client's key fingerprint is supplied out-of-band.** Clients receive their own fingerprint via the `--keyid` command-line flag or the `GPGCHAIN_KEYID` environment variable. Neither the server nor any network peer provides this value.
- **Revocation is irreversible.** A revoked key has no outgoing trust and a score of zero regardless of how many valid paths lead to it.
- **Cryptographic independence.** When fetching remote blocks for cross-ledger traversal, the client verifies every block's hash and every signature before using the material. The `source_node` URL is a hint only; it is not trusted.

---

## Definitions

- **Trust graph**: a directed graph where an edge A → B means "key A has signed key B". Each edge corresponds to a SigEntry in B's sig chain where `signer_fingerprint` = A.
- **Trust path**: a sequence of edges from the root fingerprint to a target fingerprint, following the direction of signing.
- **Trust score**: the number of distinct non-revoked trust paths from the root to a target within the configured depth limit.
- **Trusted**: a key is trusted if its trust score is greater than or equal to the configured threshold. Default threshold is 1.
- **Depth**: the number of hops from the root to the target. A key directly signed by the root is at depth 1. A key signed by a key at depth 1 is at depth 2. The root itself is at depth 0.
- **On-ledger signer**: a signer with a block on the local ledger. The signer's `signer_armored_key` field is empty.
- **Off-ledger signer**: a signer without a block on the local ledger. Their armored public key is stored inline in the SigEntry's `signer_armored_key` field.

---

## Graph Construction

Given a set of Block objects (the local ledger), construct a directed adjacency map as follows:

1. For each Block B in the ledger:
   - If B is revoked: add B's fingerprint to the `revoked_set`. Do not add any outgoing edges from B.
   - If B is not revoked: for each SigEntry S in B's sig chain:
     - If S.signer_fingerprint is in `revoked_set`: skip (revoked keys have no outgoing trust edges).
     - Otherwise: add the directed edge S.signer_fingerprint → B.fingerprint to the adjacency map.

2. **Revoked blocks as target nodes:** A block that is revoked is in the `revoked_set`. It can appear as the target of edges in the graph (other keys may have signed it before revocation), but it will never be scored as trusted because of the revocation check in the scoring algorithm.

3. **Off-ledger signers in the graph:** Off-ledger signers (where `signer_armored_key` is populated) are added to the graph as source nodes of edges, exactly as on-ledger signers. However, whether their outgoing edges contribute to a path depends on whether the client can establish the off-ledger signer's trustworthiness (see Off-Ledger Signers section).

4. The `revoked_set` is constructed in a single pass over all blocks before building edges. A signer whose block is revoked is excluded from contributing edges regardless of when the revocation occurred.

---

## BFS Scoring Algorithm

The scoring algorithm counts the number of distinct non-revoked paths from the root fingerprint to a target fingerprint within the depth limit. Each path is counted at most once regardless of how many times it is independently discovered.

```python
def score(target_fp, root_fp, graph, revoked_set, max_depth) -> int:
    """
    Count distinct non-revoked paths from root_fp to target_fp within max_depth hops.

    graph       : dict mapping fingerprint -> list of fingerprints it has signed
    revoked_set : set of revoked fingerprints
    max_depth   : maximum number of hops from root to target (inclusive)
    """
    if target_fp in revoked_set:
        return 0
    if target_fp == root_fp:
        return 1

    path_count = 0
    # Queue entries: (current_fp, depth, path_as_frozenset_of_visited_fingerprints)
    queue = deque([(root_fp, 0, frozenset([root_fp]))])

    while queue:
        current_fp, depth, path = queue.popleft()

        if depth >= max_depth:
            continue

        for signed_fp in graph.get(current_fp, []):
            if signed_fp in path:
                continue           # cycle prevention: skip fingerprints already in this path
            if signed_fp in revoked_set:
                continue           # dead end: revoked keys contribute no paths
            if signed_fp == target_fp:
                path_count += 1    # found a complete path; do not explore further from target
            else:
                queue.append((signed_fp, depth + 1, path | frozenset([signed_fp])))

    return path_count
```

### Key Properties

- **Path identity:** Two paths are distinct if they visit a different set of intermediate nodes. The frozenset carried with each queue entry captures the set of fingerprints in the current path and is used both for cycle prevention and for distinguishing paths.
- **No exploration past target:** When `signed_fp == target_fp`, the path is counted and the BFS does not enqueue target_fp for further exploration. This prevents phantom multi-hop paths through the target.
- **Depth semantics:** `depth` is the number of hops taken so far. When `depth == max_depth`, no further hops are allowed. A target found at `depth == max_depth` (i.e. the hop that would reach it counts it exactly once) is: the target is found by the `signed_fp == target_fp` check inside the loop before `depth >= max_depth` would block it, because `depth` represents the depth of `current_fp`, not `signed_fp`. So a target found at step `depth + 1` where `depth + 1 == max_depth` is counted (depth check fires on next dequeue if enqueued, but we never enqueue target_fp).

---

## Cycle Detection

- Each BFS exploration path tracks the full set of fingerprints visited so far as a frozenset.
- Before enqueuing a neighbour, the algorithm checks whether that fingerprint is already in the current path's frozenset.
- If it is: the neighbour is skipped (not enqueued). This breaks the cycle without affecting other paths.
- This approach allows the same node to appear in multiple distinct paths (via different routes), while preventing any single path from visiting the same node twice.
- The root fingerprint is included in the initial frozenset so that the root itself cannot be revisited mid-path.

---

## Depth Limit

- `max_depth` is configurable per evaluation call. The default is 2.
- Depth 0: only the root key itself (score is 1 for root, 0 for everything else when max_depth=0).
- Depth 1: keys directly signed by the root. The root's direct signatures contribute paths.
- Depth 2: keys signed by keys that were signed by the root. Two-hop paths are considered.
- Higher depths: extend transitively. There is no architectural maximum, but large depths may be computationally expensive on large ledgers.
- The depth limit applies **cumulatively** across ledger boundaries during cross-ledger traversal. A hop to a remote ledger consumes depth budget just as a local hop does.

---

## Revoked Node Handling

- **Revoked target:** If `target_fp` is in `revoked_set`, `score()` returns 0 immediately, regardless of how many paths reach it.
- **Revoked signer (edge source):** If a signer's fingerprint is in `revoked_set`, all edges originating from that signer are excluded from the graph during graph construction. They contribute no paths to any target.
- **Revoked intermediate node:** If a node that would appear mid-path is in `revoked_set`, the BFS skips it (`if signed_fp in revoked_set: continue`). Any path that would pass through a revoked intermediate node is broken and does not count.
- **Summary:** Revocation is transitive in the negative direction. A revoked key poisons all paths that pass through it or terminate at it, but does not affect paths that bypass it entirely.

---

## Off-Ledger Signers

An off-ledger signer is a key whose block does not exist on the local ledger but who has signed a block on the local ledger. Their public key is stored inline in the SigEntry's `signer_armored_key` field.

For trust graph traversal, an off-ledger signer's outgoing edge is counted if and only if the client can establish the signer's trustworthiness by one of two means:

### Condition A: Signer is in Local GPG Keyring as Trusted

The client checks their local GPG keyring for the signer's key. If the key is present and is locally trusted (i.e. the client has assigned it owner-trust or ultimate trust in their keyring), then the signer's edge contributes a path.

This is a local-only check. The client's keyring is a pre-existing out-of-band trust source.

### Condition B: Cross-Ledger Trust Traversal via source_node

If the SigEntry has a non-empty `source_node` field, the client may fetch the signer's block from that URL and evaluate whether the signer is trusted on the remote ledger using the same BFS algorithm. If the signer's block on the remote ledger has a trust score ≥ the configured threshold, the signer's edge contributes a path.

If neither condition A nor condition B is satisfied, the off-ledger signer contributes no paths. The edge exists in the graph but is treated as if the signer's in-degree is zero (no one trusts them).

---

## Cross-Ledger Traversal

When following an off-ledger signer path via `source_node`:

1. **Fetch:** GET `<source_node>/block/<signer_fingerprint>`. If the request fails or returns non-200, silently skip this path.
2. **Verify hash:** Compute the block hash from the fetched block's fields per `data-model.md`. If it does not match the block's own `hash` field, discard and skip.
3. **Verify self-sig:** Verify the block's `self_sig` against its `armored_key` using the SUBMIT payload. If verification fails, discard and skip.
4. **Continue BFS:** Add the remote block's SigEntries to the traversal. Each hop from the remote ledger consumes depth budget. The depth counter is not reset at ledger boundaries.
5. **Cycle prevention:** Track visited `(node_url, fingerprint)` pairs globally across the entire evaluation call. If a `(node_url, fingerprint)` pair has already been visited in the current evaluation, skip it.
6. **Memory scope:** Remote blocks are cached in memory only for the duration of the single `score()` or `trusted_set()` evaluation call. They are not persisted to the local store.
7. **Error handling:** Any network error, HTTP error, hash mismatch, or signature failure causes the specific remote path to be silently skipped. The overall evaluation continues with remaining paths.
8. **Recursion:** Cross-ledger traversal may itself encounter off-ledger signers with their own `source_node` values. These are followed recursively under the same depth budget and with the same global visited set.

---

## trusted_set

`trusted_set(root_fp, ledger, revoked_set, max_depth, threshold) -> set of fingerprints`

Returns the set of all fingerprints reachable from `root_fp` with a trust score ≥ `threshold` within `max_depth` hops.

The naive implementation calls `score()` for each fingerprint on the ledger. An efficient implementation performs a single BFS from the root and accumulates reachable nodes, then filters by whether the number of distinct paths to each node meets the threshold.

The root fingerprint itself is always considered trusted (score = 1) if it is not revoked.

### Implementation Note for Efficient trusted_set

For the common case of `threshold = 1`, a simple BFS from the root collecting all reachable non-revoked nodes within `max_depth` is sufficient. For `threshold > 1`, the multi-path counting in `score()` is required per target node.

---

## Vertex-Disjoint Path Scoring

The standard `score()` function counts all distinct paths (paths visiting a different set of intermediate nodes). However, paths that share an intermediate node are not independent: if that shared node is compromised or colluded, all paths through it are compromised simultaneously.

**Vertex-disjoint scoring** counts only the maximum number of paths that share no intermediate nodes (excluding root and target). This is a stronger measure of independence and is recommended when threshold > 1 and Sybil resistance matters.

### Definition

Two paths from root R to target T are **vertex-disjoint** if they share no intermediate nodes (nodes other than R and T themselves). The vertex-disjoint score is the maximum number of such pairwise vertex-disjoint paths.

### Algorithm

Vertex-disjoint path counting is equivalent to a maximum-flow problem. Use the standard **node-splitting** technique to enforce vertex capacity constraints:

1. **Split each intermediate node** `v` into two nodes `v_in` and `v_out` with a directed edge `v_in → v_out` of capacity 1. This enforces that each intermediate node can be used by at most one path.
2. **Root and target nodes** are not split (or are given infinite capacity).
3. **Original edges** `u → v` become edges `u_out → v_in` with infinite capacity.
4. Run **max-flow** from `root_out` to `target_in`.
5. The max-flow value is the vertex-disjoint path count.

```python
def disjoint_score(target_fp, root_fp, graph, revoked_set, max_depth) -> int:
    """
    Count maximum vertex-disjoint paths from root_fp to target_fp within max_depth hops.
    Uses node-splitting max-flow. Returns 0 for revoked targets or root == target.

    graph       : dict mapping fingerprint -> list of fingerprints it has signed
    revoked_set : set of revoked fingerprints
    max_depth   : maximum number of hops from root to target (inclusive)
    """
    if target_fp in revoked_set:
        return 0
    if target_fp == root_fp:
        return 0  # disjoint score is undefined for self; callers treat root as always trusted

    # Collect reachable nodes within max_depth (standard BFS to bound the graph)
    reachable = set()
    queue = deque([(root_fp, 0)])
    visited_bfs = {root_fp}
    while queue:
        node, depth = queue.popleft()
        reachable.add(node)
        if depth < max_depth:
            for nbr in graph.get(node, []):
                if nbr not in visited_bfs and nbr not in revoked_set:
                    visited_bfs.add(nbr)
                    queue.append((nbr, depth + 1))

    if target_fp not in reachable:
        return 0

    # Build node-split flow network.
    # Each node v (except root and target) becomes v+"_in" and v+"_out" with cap 1.
    # Root and target have infinite internal capacity (modelled as cap = len(reachable)+1).
    INF = len(reachable) + 1
    capacity = {}  # (u, v) -> capacity

    def add_edge(u, v, cap):
        capacity[(u, v)] = capacity.get((u, v), 0) + cap
        if (v, u) not in capacity:
            capacity[(v, u)] = 0

    for node in reachable:
        if node == root_fp or node == target_fp:
            add_edge(node + "_in", node + "_out", INF)
        else:
            add_edge(node + "_in", node + "_out", 1)
        for nbr in graph.get(node, []):
            if nbr in reachable and nbr not in revoked_set:
                add_edge(node + "_out", nbr + "_in", INF)

    source = root_fp + "_out"
    sink   = target_fp + "_in"

    # BFS-based max-flow (Edmonds-Karp)
    def bfs_path(cap, src, snk):
        parent = {src: None}
        q = deque([src])
        while q:
            u = q.popleft()
            if u == snk:
                path, node = [], snk
                while parent[node] is not None:
                    path.append((parent[node], node))
                    node = parent[node]
                return path[::-1]
            for (a, b), c in cap.items():
                if a == u and b not in parent and c > 0:
                    parent[b] = a
                    q.append(b)
        return None

    flow = 0
    while True:
        path = bfs_path(capacity, source, sink)
        if path is None:
            break
        bottleneck = min(capacity[e] for e in path)
        for (u, v) in path:
            capacity[(u, v)] -= bottleneck
            capacity[(v, u)] += bottleneck
        flow += bottleneck

    return flow
```

### Key Properties

- **Stronger independence guarantee:** A threshold of 2 with disjoint scoring means there are two genuinely independent trust paths — no single intermediate node can vouch for both.
- **Sybil resistance:** An attacker who controls K nodes can create at most K colluding paths. Disjoint scoring with threshold T requires them to control at least T independent nodes, making Sybil attacks T times more expensive.
- **Standard score vs disjoint score:** For threshold = 1, both algorithms are equivalent. For threshold ≥ 2, disjoint scoring is more conservative. Clients should document which algorithm they use.
- **Computational cost:** O(V × E) where V and E are the vertices and edges of the reachable subgraph. In practice the ledger subgraph is small and this is fast.
- **Root self-score:** The disjoint score of the root key with itself is not defined by this algorithm. Callers must treat the root as unconditionally trusted (as with the standard score).
