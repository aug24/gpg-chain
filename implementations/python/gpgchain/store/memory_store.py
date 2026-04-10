"""In-memory store for tests only."""
from gpgchain.chain.models import Block, SigEntry


class MemoryStore:

    def __init__(self):
        self._blocks: dict[str, Block] = {}

    def add(self, block: Block) -> None:
        if block.fingerprint in self._blocks:
            raise ValueError(f"Block already exists for fingerprint: {block.fingerprint}")
        self._blocks[block.fingerprint] = block

    def get(self, fingerprint: str) -> Block | None:
        return self._blocks.get(fingerprint)

    def all(self) -> list[Block]:
        return list(self._blocks.values())

    def add_sig(self, fingerprint: str, entry: SigEntry) -> None:
        block = self._blocks.get(fingerprint)
        if block is None:
            raise KeyError(f"No block found for fingerprint: {fingerprint}")
        block.sig_entries.append(entry)
        block.sig_chain_head = entry.hash

    def revoke(self, fingerprint: str, revocation_sig: str) -> None:
        block = self._blocks.get(fingerprint)
        if block is None:
            raise KeyError(f"No block found for fingerprint: {fingerprint}")
        block.revoked = True
        block.revocation_sig = revocation_sig

    def hashes(self) -> dict[str, str]:
        return {fp: block.sig_chain_head for fp, block in self._blocks.items()}
