"""Client-side key discovery across multiple nodes.

Implements BFS over the peer graph: try each node for the requested key; on
miss, consult /.well-known/gpgchain.json to learn peers and enqueue them.

When a TrustConfig is supplied, trust is evaluated incrementally as blocks are
found.  The search stops as soon as the threshold is met, so in the common case
(block present and already trusted on the first matching node) only one node is
contacted.  The full BFS is only run when trust cannot be established from
earlier nodes.

Domain prioritisation ensures domain-specific nodes are tried before allow-all
nodes, which are tried before unrelated nodes.
"""
from collections import deque
from dataclasses import dataclass, field

import requests


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TrustConfig:
    """Trust evaluation parameters passed to find_block."""
    root_fp: str
    threshold: int = 1
    max_depth: int = 2


@dataclass
class BlockResult:
    """Result of a find_block search.

    Attributes:
        found:       True if the block was located on at least one node.
        node_url:    URL of the node that returned the most complete copy
                     (longest sig chain).  Empty string if not found.
        block:       The block dict from that node.  None if not found.
        nodes_tried: Number of nodes contacted during the search.
        trust_score: Trust score at the point the search stopped, or None if
                     no TrustConfig was supplied.
        all_copies:  Every (node_url, block) pair where the block was found,
                     in discovery order.  Useful for cross-validation.
    """
    found: bool
    node_url: str
    block: dict | None
    nodes_tried: int
    trust_score: int | None = None
    all_copies: list[tuple[str, dict]] = field(default_factory=list)


@dataclass
class EmailResult:
    """Result of a find_blocks_by_email search.

    Attributes:
        blocks:      List of (node_url, block) pairs, deduplicated by
                     fingerprint.  For each fingerprint the copy with the
                     longest sig chain is kept.
        nodes_tried: Number of nodes contacted during the search.
    """
    blocks: list[tuple[str, dict]]
    nodes_tried: int

    @property
    def found(self) -> bool:
        return bool(self.blocks)


# ---------------------------------------------------------------------------
# Inline trust scoring (avoids importing chain.models in client code)
# ---------------------------------------------------------------------------

def _build_trust_graph(block_dicts) -> tuple[dict, set]:
    """Build a trust graph from raw block dicts.

    Returns (graph, revoked_set) where graph maps signer_fp → set of fps
    that signer has vouched for (edges only for non-revoked signers/targets).
    """
    revoked: set[str] = {
        b["fingerprint"] for b in block_dicts if b.get("revoked")
    }
    graph: dict[str, set[str]] = {}
    for b in block_dicts:
        if b.get("revoked"):
            continue
        for sig in b.get("sig_chain", []):
            sfp = sig.get("signer_fingerprint", "")
            if sfp and sfp not in revoked:
                graph.setdefault(sfp, set()).add(b["fingerprint"])
    return graph, revoked


def _trust_score(
    graph: dict,
    target_fp: str,
    root_fp: str,
    max_depth: int,
    revoked: set,
) -> int:
    """Count distinct non-revoked paths from root_fp to target_fp."""
    if target_fp in revoked:
        return 0
    if target_fp == root_fp:
        return 1
    count = 0
    queue: deque = deque([(root_fp, 0, frozenset([root_fp]))])
    while queue:
        cur, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for nbr in graph.get(cur, set()):
            if nbr in path or nbr in revoked:
                continue
            if nbr == target_fp:
                count += 1
            else:
                queue.append((nbr, depth + 1, path | {nbr}))
    return count


# ---------------------------------------------------------------------------
# BFS helpers
# ---------------------------------------------------------------------------

def _enqueue_peers_from_wk(
    wk_data: dict,
    target_domain: str,
    exact: deque,
    allow_all: deque,
    normal: deque,
    visited: set,
) -> None:
    """Enqueue peers from a well-known response into the appropriate queue.

    Priority order (highest first):
      exact     — peer explicitly declares the target domain
      allow_all — peer accepts all domains (allow_all: true)
      normal    — peer scoped to unrelated domains, or metadata not yet known
    """
    peer_nodes = wk_data.get("peer_nodes")
    if peer_nodes is not None:
        for pn in peer_nodes:
            url = pn.get("url", "").rstrip("/")
            if not url or url in visited:
                continue
            visited.add(url)
            if target_domain and target_domain in pn.get("domains", []):
                exact.append(url)
            elif target_domain and pn.get("allow_all", False):
                allow_all.append(url)
            else:
                normal.append(url)
    else:
        for url in wk_data.get("peers", []):
            url = url.rstrip("/")
            if not url or url in visited:
                continue
            visited.add(url)
            normal.append(url)


def _next(exact: deque, allow_all: deque, normal: deque) -> str:
    if exact:
        return exact.popleft()
    if allow_all:
        return allow_all.popleft()
    return normal.popleft()


def _best_copy(copies: list[tuple[str, dict]]) -> tuple[str, dict]:
    """Return the copy with the longest sig chain."""
    return max(copies, key=lambda p: len(p[1].get("sig_chain", [])))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_block(
    fingerprint: str,
    seed_nodes: list[str],
    domain_hint: str = "",
    max_nodes: int = 20,
    timeout: float = 5.0,
    trust: TrustConfig | None = None,
) -> BlockResult:
    """Find a block by fingerprint, fanning out across the peer graph.

    When trust is None (default):
        Full BFS — every reachable node is tried (up to max_nodes).  The copy
        with the longest sig chain is returned.

    When trust is provided:
        Trust is evaluated after each node that returns the target block.  The
        search stops as soon as the score meets trust.threshold, so in the
        happy path only one node is contacted.  Blocks fetched from productive
        nodes are accumulated into a shared trust context and re-evaluated at
        each step, so trust paths that span multiple nodes are also discovered.
        Only nodes that have the target block trigger the expensive GET /blocks
        call; nodes that return 404 only contribute their peer list.

    Nodes are tried in domain-priority order:
      1. Nodes that explicitly declare domain_hint
      2. Nodes that accept all domains (allow_all: true)
      3. Everything else
    """
    visited: set[str] = set()
    exact: deque[str] = deque()
    wildcard: deque[str] = deque()
    normal: deque[str] = deque()
    copies: list[tuple[str, dict]] = []
    # Blocks accumulated from all productive nodes, keyed by fingerprint.
    # Used to build an incrementally growing trust graph.
    accumulated: dict[str, dict] = {}

    def _seed(url: str) -> None:
        url = url.rstrip("/")
        if url not in visited:
            visited.add(url)
            normal.append(url)

    for url in seed_nodes:
        _seed(url)

    while (exact or wildcard or normal) and len(visited) <= max_nodes:
        url = _next(exact, wildcard, normal)

        # --- Try to fetch the target block ---
        try:
            resp = requests.get(f"{url}/block/{fingerprint}", timeout=timeout)
            if resp.status_code == 200:
                block = resp.json()
                copies.append((url, block))

                if trust is not None:
                    # Fetch all blocks from this node to build trust context.
                    try:
                        all_resp = requests.get(
                            f"{url}/blocks", timeout=timeout
                        )
                        if all_resp.status_code == 200:
                            for b in all_resp.json():
                                fp2 = b.get("fingerprint", "")
                                if not fp2:
                                    continue
                                existing = accumulated.get(fp2)
                                if existing is None or len(
                                    b.get("sig_chain", [])
                                ) > len(existing.get("sig_chain", [])):
                                    accumulated[fp2] = b
                    except Exception:
                        pass

                    graph, revoked = _build_trust_graph(accumulated.values())
                    sc = _trust_score(
                        graph, fingerprint, trust.root_fp,
                        trust.max_depth, revoked,
                    )
                    if sc >= trust.threshold:
                        best_url, best_block = _best_copy(copies)
                        return BlockResult(
                            found=True,
                            node_url=best_url,
                            block=best_block,
                            nodes_tried=len(visited),
                            trust_score=sc,
                            all_copies=copies,
                        )
        except Exception:
            pass

        # --- Discover peers ---
        try:
            wk = requests.get(
                f"{url}/.well-known/gpgchain.json", timeout=timeout
            )
            if wk.status_code == 200:
                _enqueue_peers_from_wk(
                    wk.json(), domain_hint, exact, wildcard, normal, visited
                )
        except Exception:
            pass

    # BFS exhausted.
    if not copies:
        return BlockResult(
            found=False,
            node_url="",
            block=None,
            nodes_tried=len(visited),
            trust_score=0 if trust is not None else None,
        )

    best_url, best_block = _best_copy(copies)
    final_score: int | None = None
    if trust is not None:
        graph, revoked = _build_trust_graph(accumulated.values())
        final_score = _trust_score(
            graph, fingerprint, trust.root_fp, trust.max_depth, revoked
        )
    return BlockResult(
        found=True,
        node_url=best_url,
        block=best_block,
        nodes_tried=len(visited),
        trust_score=final_score,
        all_copies=copies,
    )


def find_blocks_by_email(
    email: str,
    seed_nodes: list[str],
    max_nodes: int = 20,
    timeout: float = 5.0,
) -> EmailResult:
    """Search for blocks matching an email address across the peer graph.

    Visits every reachable node (BFS, up to max_nodes) and collects all
    matching blocks.  Deduplicates by fingerprint; for each fingerprint the
    copy with the longest sig chain is kept.

    Nodes are tried in domain-priority order (see find_block).

    Always returns an EmailResult; check .found to determine whether anything
    was located.  .nodes_tried is set regardless.
    """
    domain = email.split("@")[-1] if "@" in email else ""

    visited: set[str] = set()
    exact: deque[str] = deque()
    wildcard: deque[str] = deque()
    normal: deque[str] = deque()
    best: dict[str, tuple[str, dict]] = {}  # fp → (node_url, block)

    def _seed(url: str) -> None:
        url = url.rstrip("/")
        if url not in visited:
            visited.add(url)
            normal.append(url)

    for url in seed_nodes:
        _seed(url)

    while (exact or wildcard or normal) and len(visited) <= max_nodes:
        url = _next(exact, wildcard, normal)
        try:
            resp = requests.get(
                f"{url}/search", params={"q": email}, timeout=timeout
            )
            if resp.status_code == 200:
                for block in resp.json():
                    fp = block.get("fingerprint", "")
                    if not fp:
                        continue
                    existing = best.get(fp)
                    if existing is None or len(
                        block.get("sig_chain", [])
                    ) > len(existing[1].get("sig_chain", [])):
                        best[fp] = (url, block)
        except Exception:
            pass

        try:
            wk = requests.get(
                f"{url}/.well-known/gpgchain.json", timeout=timeout
            )
            if wk.status_code == 200:
                _enqueue_peers_from_wk(
                    wk.json(), domain, exact, wildcard, normal, visited
                )
        except Exception:
            pass

    return EmailResult(blocks=list(best.values()), nodes_tried=len(visited))
