"""Sync-on-connect and periodic cross-validation."""


class Sync:

    def __init__(self, store, peers):
        self._store = store
        self._peers = peers

    def sync_with_peer(self, peer_url: str) -> None:
        """Fetch /p2p/hashes from peer, request and verify missing blocks."""
        raise NotImplementedError

    def cross_validate(self) -> list[str]:
        """Compare {fp: sig_chain_head} across all peers.

        Returns list of fingerprints where peers disagree (possible censorship).
        """
        raise NotImplementedError
