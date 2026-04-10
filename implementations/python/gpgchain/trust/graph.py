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


def score(
    graph: TrustGraph,
    target_fp: str,
    root_fp: str,
    max_depth: int = 2,
    revoked_set: set[str] | None = None,
) -> int:
    """Count distinct non-revoked trust paths from root_fp to target_fp within max_depth.

    Uses BFS with per-path visited tracking to count all simple paths.
    Returns 0 if target is revoked or no qualifying path exists.
    """
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
) -> bool:
    """Return True if score(graph, target_fp, root_fp, max_depth, revoked_set) >= threshold."""
    return score(graph, target_fp, root_fp, max_depth, revoked_set) >= threshold


def trusted_set(
    graph: TrustGraph,
    root_fp: str,
    max_depth: int = 2,
    threshold: int = 1,
    revoked_set: set[str] | None = None,
) -> list[str]:
    """Return all fingerprints reachable from root_fp at or above threshold.

    For threshold == 1, uses a single BFS to collect all non-revoked fingerprints
    reachable from root_fp within max_depth (excluding root_fp itself).

    For threshold > 1, collects candidate fingerprints via BFS first, then calls
    score() for each candidate to filter by the required threshold.
    """
    if revoked_set is None:
        revoked_set = set()

    if threshold == 1:
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

    # threshold > 1: gather all candidate fingerprints via BFS, then score each.
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
        if score(graph, fp, root_fp, max_depth, revoked_set) >= threshold
    ]
    return sorted(result)
