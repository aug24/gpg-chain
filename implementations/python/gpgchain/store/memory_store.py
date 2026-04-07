"""In-memory store for tests only."""
from gpgchain.chain.models import Block, SigEntry


class MemoryStore:

    def __init__(self):
        self._blocks: dict[str, Block] = {}

    def add(self, block: Block) -> None:
        raise NotImplementedError

    def get(self, fingerprint: str) -> Block | None:
        raise NotImplementedError

    def all(self) -> list[Block]:
        raise NotImplementedError

    def add_sig(self, fingerprint: str, entry: SigEntry) -> None:
        raise NotImplementedError

    def revoke(self, fingerprint: str, revocation_sig: str) -> None:
        raise NotImplementedError

    def hashes(self) -> dict[str, str]:
        raise NotImplementedError
