"""Directory tree store with LRU cache.

Layout:
    <store_dir>/<fp[0:2]>/<fp[2:4]>/<fp>.block.json
    <store_dir>/<fp[0:2]>/<fp[2:4]>/<fp>.sig.<sighash>.json
    <store_dir>/<fp[0:2]>/<fp[2:4]>/<fp>.revoke.json

All writes are atomic: write to <path>.tmp then os.rename into place.
Reads go through a cachetools.LRUCache keyed by fingerprint.
"""
import json
import os
from pathlib import Path

from cachetools import LRUCache

from gpgchain.chain.models import Block, SigEntry


class DirStore:

    def __init__(self, store_dir: str, prefix_len: int = 4, cache_size: int = 128):
        self._root = Path(store_dir)
        self._prefix_len = prefix_len  # total chars; split evenly into two levels
        self._cache: LRUCache = LRUCache(maxsize=cache_size)
        self._root.mkdir(parents=True, exist_ok=True)

    # --- Path helpers ---

    def _block_dir(self, fingerprint: str) -> Path:
        raise NotImplementedError

    def _block_path(self, fingerprint: str) -> Path:
        raise NotImplementedError

    def _sig_path(self, fingerprint: str, sig_hash: str) -> Path:
        raise NotImplementedError

    def _revoke_path(self, fingerprint: str) -> Path:
        raise NotImplementedError

    def _atomic_write(self, path: Path, data: dict) -> None:
        raise NotImplementedError

    # --- Store protocol ---

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
