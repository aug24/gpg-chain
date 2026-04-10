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
import time
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
        half = self._prefix_len // 2
        level1 = fingerprint[0:half]
        level2 = fingerprint[half:self._prefix_len]
        return self._root / level1 / level2

    def _block_path(self, fingerprint: str) -> Path:
        return self._block_dir(fingerprint) / f"{fingerprint}.block.json"

    def _sig_path(self, fingerprint: str, sig_hash: str) -> Path:
        return self._block_dir(fingerprint) / f"{fingerprint}.sig.{sig_hash}.json"

    def _revoke_path(self, fingerprint: str) -> Path:
        return self._block_dir(fingerprint) / f"{fingerprint}.revoke.json"

    def _atomic_write(self, path: Path, data: dict) -> None:
        tmp_path = Path(str(path) + ".tmp")
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp_path, path)

    # --- Store protocol ---

    def add(self, block: Block) -> None:
        block_path = self._block_path(block.fingerprint)
        if block_path.exists():
            raise ValueError(f"Block already exists for fingerprint: {block.fingerprint}")
        block_dir = self._block_dir(block.fingerprint)
        block_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "hash": block.hash,
            "fingerprint": block.fingerprint,
            "armored_key": block.armored_key,
            "uids": block.uids,
            "submit_timestamp": block.submit_timestamp,
            "self_sig": block.self_sig,
            "revoked": block.revoked,
            "revocation_sig": block.revocation_sig,
        }
        self._atomic_write(block_path, data)

    def get(self, fingerprint: str) -> Block | None:
        # 1. Check LRU cache
        if fingerprint in self._cache:
            return self._cache[fingerprint]

        # 2. Read block.json
        block_path = self._block_path(fingerprint)
        if not block_path.exists():
            return None
        data = json.loads(block_path.read_text(encoding="utf-8"))
        block = Block(
            hash=data["hash"],
            fingerprint=data["fingerprint"],
            armored_key=data["armored_key"],
            uids=data.get("uids", []),
            submit_timestamp=data.get("submit_timestamp", 0),
            self_sig=data.get("self_sig", ""),
            revoked=data.get("revoked", False),
            revocation_sig=data.get("revocation_sig", ""),
        )

        # 3. Enumerate sig files
        block_dir = self._block_dir(fingerprint)
        sig_entries: list[SigEntry] = []
        for sig_file in block_dir.glob(f"{fingerprint}.sig.*.json"):
            sig_data = json.loads(sig_file.read_text(encoding="utf-8"))
            entry = SigEntry(
                hash=sig_data["hash"],
                prev_hash=sig_data["prev_hash"],
                signer_fingerprint=sig_data["signer_fingerprint"],
                sig=sig_data["sig"],
                timestamp=sig_data["timestamp"],
                signer_armored_key=sig_data.get("signer_armored_key", ""),
                source_node=sig_data.get("source_node", ""),
            )
            sig_entries.append(entry)

        # 4. Reconstruct sig chain order by following prev_hash links
        if sig_entries:
            # Build a mapping from prev_hash -> SigEntry (each entry points back to its predecessor)
            by_prev: dict[str, SigEntry] = {e.prev_hash: e for e in sig_entries}
            # The chain starts at block.hash; find the first entry whose prev_hash == block.hash
            # Walk forward: current_hash starts at block.hash, find entry where prev_hash == current_hash
            ordered: list[SigEntry] = []
            current_hash = block.hash
            visited: set[str] = set()
            while current_hash in by_prev:
                if current_hash in visited:
                    break  # cycle guard
                visited.add(current_hash)
                entry = by_prev[current_hash]
                ordered.append(entry)
                current_hash = entry.hash
            block.sig_entries = ordered
            # 5. sig_chain_head = last entry's hash
            block.sig_chain_head = ordered[-1].hash if ordered else ""
        else:
            block.sig_entries = []
            block.sig_chain_head = ""

        # 6. Check revoke file
        revoke_path = self._revoke_path(fingerprint)
        if revoke_path.exists():
            revoke_data = json.loads(revoke_path.read_text(encoding="utf-8"))
            block.revoked = True
            block.revocation_sig = revoke_data.get("revocation_sig", "")

        # 7. Cache and return
        self._cache[fingerprint] = block
        return block

    def all(self) -> list[Block]:
        blocks: list[Block] = []
        for block_file in self._root.rglob("*.block.json"):
            # Extract fingerprint from filename: <fp>.block.json
            fp = block_file.name[: -len(".block.json")]
            block = self.get(fp)
            if block is not None:
                blocks.append(block)
        return blocks

    def add_sig(self, fingerprint: str, entry: SigEntry) -> None:
        block = self.get(fingerprint)
        if block is None:
            raise KeyError(f"No block found for fingerprint: {fingerprint}")
        sig_path = self._sig_path(fingerprint, entry.hash)
        data = {
            "hash": entry.hash,
            "prev_hash": entry.prev_hash,
            "signer_fingerprint": entry.signer_fingerprint,
            "sig": entry.sig,
            "timestamp": entry.timestamp,
            "signer_armored_key": entry.signer_armored_key,
            "source_node": entry.source_node,
        }
        self._atomic_write(sig_path, data)
        # Invalidate cache
        self._cache.pop(fingerprint, None)

    def revoke(self, fingerprint: str, revocation_sig: str) -> None:
        block = self.get(fingerprint)
        if block is None:
            raise KeyError(f"No block found for fingerprint: {fingerprint}")
        revoke_path = self._revoke_path(fingerprint)
        data = {
            "revocation_sig": revocation_sig,
            "revoked_at": int(time.time()),
        }
        self._atomic_write(revoke_path, data)
        # Invalidate cache
        self._cache.pop(fingerprint, None)

    def hashes(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for block_file in self._root.rglob("*.block.json"):
            fp = block_file.name[: -len(".block.json")]
            block_dir = block_file.parent
            # Scan sig filenames to find the chain tip without loading full blocks
            sig_files = list(block_dir.glob(f"{fp}.sig.*.json"))
            if not sig_files:
                result[fp] = ""
                continue
            # Extract sig hashes from filenames: <fp>.sig.<sighash>.json
            prefix = f"{fp}.sig."
            suffix = ".json"
            all_sig_hashes: set[str] = set()
            for sf in sig_files:
                name = sf.name
                sig_hash = name[len(prefix): -len(suffix)]
                all_sig_hashes.add(sig_hash)
            # Read prev_hashes from each sig file to find which hash is not referenced as a prev_hash
            # The tip is the hash not pointed to by any other sig's prev_hash
            referenced_as_prev: set[str] = set()
            for sf in sig_files:
                sig_data = json.loads(sf.read_text(encoding="utf-8"))
                prev = sig_data.get("prev_hash", "")
                referenced_as_prev.add(prev)
            # The tip hash is in all_sig_hashes but not in referenced_as_prev
            tips = all_sig_hashes - referenced_as_prev
            if len(tips) == 1:
                result[fp] = tips.pop()
            elif tips:
                # Ambiguous — fall back to the lexicographically last tip
                result[fp] = max(tips)
            else:
                # All hashes are referenced — cycle or corrupt; return empty
                result[fp] = ""
        return result
