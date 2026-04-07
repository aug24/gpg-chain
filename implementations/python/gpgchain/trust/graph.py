"""Trust graph construction and BFS scoring.

Trust decisions are always made by the client. This module never contacts a server
to make a trust decision — it only processes data already retrieved from the ledger.
"""
from gpgchain.chain.models import Block


# Adjacency map: fingerprint -> set of fingerprints that have signed it (non-revoked only)
TrustGraph = dict[str, set[str]]


def build_graph(blocks: list[Block]) -> TrustGraph:
    """Build a trust graph from a list of blocks.

    Edges: signer_fp -> target_fp (signer vouches for target).
    Revoked blocks are included as nodes but their outgoing edges are excluded
    (a revoked key cannot vouch for others).
    Signatures from revoked signers are excluded.
    """
    raise NotImplementedError


def score(graph: TrustGraph, target_fp: str, root_fp: str, max_depth: int = 2) -> int:
    """Count distinct non-revoked trust paths from root_fp to target_fp within max_depth.

    Uses BFS. Handles cycles. Returns 0 if no path exists.
    """
    raise NotImplementedError


def is_trusted(graph: TrustGraph, target_fp: str, root_fp: str,
               max_depth: int = 2, threshold: int = 1) -> bool:
    """Return True if score >= threshold."""
    raise NotImplementedError


def trusted_set(graph: TrustGraph, root_fp: str,
                max_depth: int = 2, threshold: int = 1) -> list[str]:
    """Return all fingerprints reachable from root at or above threshold."""
    raise NotImplementedError
