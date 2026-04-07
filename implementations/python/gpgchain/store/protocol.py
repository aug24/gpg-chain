"""Store protocol (abstract interface)."""
from typing import Protocol
from gpgchain.chain.models import Block, SigEntry


class Store(Protocol):

    def add(self, block: Block) -> None:
        """Persist a new block. Raise ValueError if fingerprint already exists."""
        ...

    def get(self, fingerprint: str) -> Block | None:
        """Return the block for the given fingerprint, or None if not found."""
        ...

    def all(self) -> list[Block]:
        """Return all blocks."""
        ...

    def add_sig(self, fingerprint: str, entry: SigEntry) -> None:
        """Append a SigEntry to the block's sig chain. Raise KeyError if block not found."""
        ...

    def revoke(self, fingerprint: str, revocation_sig: str) -> None:
        """Mark a block as revoked. Raise KeyError if block not found."""
        ...

    def hashes(self) -> dict[str, str]:
        """Return {fingerprint: sig_chain_head} for all blocks. Fast — no full block load required."""
        ...
