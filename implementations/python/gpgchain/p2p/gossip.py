"""Gossip protocol: bounded fanout with seen-set."""
from gpgchain.chain.models import Block, SigEntry


class Gossip:

    def __init__(self, peers, fanout: int = 3):
        self._peers = peers
        self._fanout = fanout
        self._seen: set[str] = set()

    def gossip_block(self, block: Block, origin: str = "") -> None:
        """Forward block to K random peers, excluding origin."""
        raise NotImplementedError

    def gossip_sig(self, fingerprint: str, entry: SigEntry, origin: str = "") -> None:
        """Forward sig entry to K random peers, excluding origin."""
        raise NotImplementedError

    def gossip_revoke(self, fingerprint: str, revocation_sig: str, origin: str = "") -> None:
        """Forward revocation to K random peers, excluding origin."""
        raise NotImplementedError
