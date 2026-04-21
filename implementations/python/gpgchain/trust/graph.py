"""Trust graph construction and BFS scoring."""
from collections import deque
from gpgchain.chain.models import Block

TrustGraph = dict[str, set[str]]


def build_graph(blocks: list[Block]) -> tuple[TrustGraph, set[str]]:
    """Build a trust graph from a list of blocks.

    Returns a tuple of (graph, revoked_set) where:
    - graph maps signer_fp -> set of fingerprints the signer has vouched for
      (outgoing edges; only non-revoked signers signing non-revoked targets)
    - revoked_set is the set of all fingerprints whose block has revoked=True

    Rules:
    - First collect all revoked fingerprints.
    - For each non-revoked block B, for each SigEntry S in B.sig_entries:
        - If S.signer_fingerprint is in revoked_set: skip (dead signer)
        - Otherwise: add edge S.signer_fingerprint -> B.fingerprint
    """
    revoked_set: set[str] = {b.fingerprint for b in blocks if b.revoked}

    graph: TrustGraph = {}
    for block in blocks:
        if block.revoked:
            continue
        for sig_entry in block.sig_entries:
            if sig_entry.signer_fingerprint in revoked_set:
                continue
            graph.setdefault(sig_entry.signer_fingerprint, set()).add(block.fingerprint)

    return graph, revoked_set


def disjoint_score(
    graph: TrustGraph,
    target_fp: str,
    root_fp: str,
    max_depth: int = 2,
    revoked_set: set[str] | None = None,
) -> int:
    """Maximum number of vertex-disjoint trust paths from root_fp to target_fp.

    Paths are vertex-disjoint when they share no intermediate key. A score of N
    means no single intermediate key compromise can reduce the count by more than 1.

    Uses max-flow on a node-split network: each intermediate node v is split into
    v_in and v_out with internal capacity 1, capping flow (and thus paths) through v.
    Only edges on depth-bounded paths (dist_fwd[u] + 1 + dist_bwd[v] <= max_depth)
    are included.
    """
    if revoked_set is None:
        revoked_set = set()
    if target_fp in revoked_set:
        return 0
    if target_fp == root_fp:
        return 1

    # Forward BFS: minimum distance from root to each reachable node.
    dist_fwd: dict[str, int] = {root_fp: 0}
    bfs: deque[str] = deque([root_fp])
    while bfs:
        fp = bfs.popleft()
        d = dist_fwd[fp]
        if d >= max_depth:
            continue
        for nbr in graph.get(fp, set()):
            if nbr not in dist_fwd and nbr not in revoked_set:
                dist_fwd[nbr] = d + 1
                bfs.append(nbr)

    if target_fp not in dist_fwd:
        return 0

    # Backward BFS: minimum distance from each node back to target.
    rev: dict[str, set[str]] = {}
    for fp, nbrs in graph.items():
        for nbr in nbrs:
            rev.setdefault(nbr, set()).add(fp)

    dist_bwd: dict[str, int] = {target_fp: 0}
    bfs = deque([target_fp])
    while bfs:
        fp = bfs.popleft()
        for nbr in rev.get(fp, set()):
            if nbr not in dist_bwd and nbr not in revoked_set:
                dist_bwd[nbr] = dist_bwd[fp] + 1
                bfs.append(nbr)

    # Intermediate nodes on at least one valid depth-bounded path.
    intermediates: list[str] = sorted(
        fp for fp in dist_fwd
        if fp not in (root_fp, target_fp)
        and fp in dist_bwd
        and dist_fwd[fp] + dist_bwd[fp] <= max_depth
    )

    # Node IDs: 0 = source (root), 1 = sink (target),
    # then for each intermediate i: 2+2i = in-node, 2+2i+1 = out-node.
    inter_idx = {fp: i for i, fp in enumerate(intermediates)}
    total_nodes = 2 + 2 * len(intermediates)
    SOURCE, SINK = 0, 1

    def in_id(fp: str) -> int:
        return 2 + 2 * inter_idx[fp]

    def out_id(fp: str) -> int:
        return 2 + 2 * inter_idx[fp] + 1

    # Adjacency list flow network. Each entry: [to, capacity, rev_edge_index].
    fnet: list[list[list]] = [[] for _ in range(total_nodes)]

    def add_edge(u: int, v: int, cap: int) -> None:
        fnet[u].append([v, cap, len(fnet[v])])
        fnet[v].append([u, 0, len(fnet[u]) - 1])

    # Internal split edges (capacity 1 = vertex-disjointness constraint).
    for fp in intermediates:
        add_edge(in_id(fp), out_id(fp), 1)

    # Cross edges filtered to depth-bounded paths.
    INF = len(intermediates) + 2
    for fp1 in [root_fp] + intermediates:
        d1 = dist_fwd[fp1]
        u = SOURCE if fp1 == root_fp else out_id(fp1)
        for fp2 in graph.get(fp1, set()):
            if fp2 in revoked_set:
                continue
            d2 = dist_bwd.get(fp2, max_depth + 1)
            if d1 + 1 + d2 > max_depth:
                continue
            if fp2 == target_fp:
                v = SINK
            elif fp2 in inter_idx:
                v = in_id(fp2)
            else:
                continue
            add_edge(u, v, INF)

    # Edmonds-Karp max-flow.
    total_flow = 0
    while True:
        prev: list[tuple[int, int] | None] = [None] * total_nodes
        prev[SOURCE] = (-1, -1)
        bfs = deque([SOURCE])
        while bfs and prev[SINK] is None:
            u = bfs.popleft()
            for i, (v, cap, _) in enumerate(fnet[u]):
                if prev[v] is None and cap > 0:
                    prev[v] = (u, i)
                    bfs.append(v)
        if prev[SINK] is None:
            break
        bottleneck: int | float = float('inf')
        v = SINK
        while v != SOURCE:
            u, i = prev[v]  # type: ignore[misc]
            bottleneck = min(bottleneck, fnet[u][i][1])
            v = u
        v = SINK
        while v != SOURCE:
            u, i = prev[v]  # type: ignore[misc]
            fnet[u][i][1] -= bottleneck
            fnet[v][fnet[u][i][2]][1] += bottleneck
            v = u
        total_flow += bottleneck

    return int(total_flow)


def score(
    graph: TrustGraph,
    target_fp: str,
    root_fp: str,
    max_depth: int = 2,
    revoked_set: set[str] | None = None,
    disjoint: bool = False,
) -> int:
    """Count distinct non-revoked trust paths from root_fp to target_fp within max_depth.

    If disjoint=True, returns the maximum number of vertex-disjoint paths instead
    (see disjoint_score()).

    Uses BFS with per-path visited tracking to count all simple paths.
    Returns 0 if target is revoked or no qualifying path exists.
    """
    if disjoint:
        return disjoint_score(graph, target_fp, root_fp, max_depth, revoked_set)

    if revoked_set is None:
        revoked_set = set()

    if target_fp in revoked_set:
        return 0
    if target_fp == root_fp:
        return 1

    path_count = 0
    # Each queue item: (current_fp, current_depth, frozenset of fps visited on this path)
    queue: deque[tuple[str, int, frozenset[str]]] = deque(
        [(root_fp, 0, frozenset([root_fp]))]
    )

    while queue:
        current_fp, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for signed_fp in graph.get(current_fp, set()):
            if signed_fp in path:
                continue  # cycle prevention
            if signed_fp in revoked_set:
                continue  # dead end
            if signed_fp == target_fp:
                path_count += 1  # found a complete path; don't explore further
            else:
                queue.append((signed_fp, depth + 1, path | frozenset([signed_fp])))

    return path_count


def is_trusted(
    graph: TrustGraph,
    target_fp: str,
    root_fp: str,
    max_depth: int = 2,
    threshold: int = 1,
    revoked_set: set[str] | None = None,
    disjoint: bool = False,
) -> bool:
    """Return True if score(graph, target_fp, root_fp, max_depth, revoked_set, disjoint) >= threshold."""
    return score(graph, target_fp, root_fp, max_depth, revoked_set, disjoint) >= threshold


def trusted_set(
    graph: TrustGraph,
    root_fp: str,
    max_depth: int = 2,
    threshold: int = 1,
    revoked_set: set[str] | None = None,
    disjoint: bool = False,
) -> list[str]:
    """Return all fingerprints reachable from root_fp at or above threshold.

    For threshold == 1 and disjoint == False, uses a single BFS to collect all
    non-revoked fingerprints reachable from root_fp within max_depth (excluding
    root_fp itself).

    For threshold > 1 or disjoint == True, collects candidate fingerprints via BFS
    first, then calls score() for each candidate to filter by the required threshold.
    """
    if revoked_set is None:
        revoked_set = set()

    if threshold == 1 and not disjoint:
        # Simple BFS: collect all reachable non-revoked fingerprints within max_depth.
        visited: set[str] = set()
        # Queue items: (fp, depth)
        queue: deque[tuple[str, int]] = deque([(root_fp, 0)])
        seen: set[str] = {root_fp}

        while queue:
            current_fp, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for signed_fp in graph.get(current_fp, set()):
                if signed_fp in revoked_set:
                    continue
                if signed_fp not in seen:
                    seen.add(signed_fp)
                    visited.add(signed_fp)
                    queue.append((signed_fp, depth + 1))

        return sorted(visited)

    # threshold > 1 or disjoint: gather all candidate fingerprints via BFS, then score each.
    candidates: set[str] = set()
    bfs_queue: deque[tuple[str, int]] = deque([(root_fp, 0)])
    bfs_seen: set[str] = {root_fp}

    while bfs_queue:
        current_fp, depth = bfs_queue.popleft()
        if depth >= max_depth:
            continue
        for signed_fp in graph.get(current_fp, set()):
            if signed_fp in revoked_set:
                continue
            if signed_fp not in bfs_seen:
                bfs_seen.add(signed_fp)
                candidates.add(signed_fp)
                bfs_queue.append((signed_fp, depth + 1))

    result = [
        fp for fp in candidates
        if score(graph, fp, root_fp, max_depth, revoked_set, disjoint) >= threshold
    ]
    return sorted(result)
