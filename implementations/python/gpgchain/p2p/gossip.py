"""Gossip protocol: bounded fanout with seen-set."""
import random
import time

import httpx

from gpgchain.chain.models import Block, SigEntry

_SEEN_TTL = 3600  # 1 hour


def _sig_entry_to_dict(entry: SigEntry) -> dict:
    d = {
        "hash": entry.hash,
        "prev_hash": entry.prev_hash,
        "signer_fingerprint": entry.signer_fingerprint,
        "sig": entry.sig,
        "timestamp": entry.timestamp,
    }
    if entry.signer_armored_key:
        d["signer_armored_key"] = entry.signer_armored_key
    if entry.source_node:
        d["source_node"] = entry.source_node
    return d


def block_to_dict(block: Block) -> dict:
    return {
        "hash": block.hash,
        "fingerprint": block.fingerprint,
        "armored_key": block.armored_key,
        "uids": block.uids,
        "submit_timestamp": block.submit_timestamp,
        "self_sig": block.self_sig,
        "sig_chain_head": block.sig_chain_head,
        "sig_chain": [_sig_entry_to_dict(e) for e in block.sig_entries],
        "revoked": block.revoked,
        "revocation_sig": block.revocation_sig,
    }


class Gossip:

    def __init__(self, peers: list, fanout: int = 3):
        self._peers = peers        # direct reference to app.state.peer_list
        self._fanout = fanout
        self._seen: dict[str, float] = {}  # event_id -> time added

    def _is_seen(self, event_id: str) -> bool:
        ts = self._seen.get(event_id)
        if ts is None:
            return False
        if time.monotonic() - ts > _SEEN_TTL:
            del self._seen[event_id]
            return False
        return True

    def _mark_seen(self, event_id: str) -> None:
        self._seen[event_id] = time.monotonic()

    def _pick_targets(self, origin: str = "") -> list[str]:
        candidates = [p for p in self._peers if p != origin]
        k = min(self._fanout, len(candidates))
        return random.sample(candidates, k) if k > 0 else []

    def gossip_block(self, block: Block, origin: str = "") -> None:
        """Forward block to K random peers, excluding origin."""
        if self._is_seen(block.hash):
            return
        self._mark_seen(block.hash)
        body = {"block": block_to_dict(block)}
        for peer in self._pick_targets(origin):
            try:
                httpx.post(f"{peer.rstrip('/')}/p2p/block", json=body, timeout=5.0)
            except Exception:
                pass

    def gossip_sig(self, fingerprint: str, entry: SigEntry, origin: str = "") -> None:
        """Forward sig entry to K random peers, excluding origin."""
        if self._is_seen(entry.hash):
            return
        self._mark_seen(entry.hash)
        body = {"fingerprint": fingerprint, "entry": _sig_entry_to_dict(entry)}
        for peer in self._pick_targets(origin):
            try:
                httpx.post(f"{peer.rstrip('/')}/p2p/sign", json=body, timeout=5.0)
            except Exception:
                pass

    def gossip_revoke(self, fingerprint: str, revocation_sig: str, origin: str = "") -> None:
        """Forward revocation to K random peers, excluding origin."""
        event_id = f"{fingerprint}.revoke"
        if self._is_seen(event_id):
            return
        self._mark_seen(event_id)
        body = {"fingerprint": fingerprint, "revocation_sig": revocation_sig}
        for peer in self._pick_targets(origin):
            try:
                httpx.post(f"{peer.rstrip('/')}/p2p/revoke", json=body, timeout=5.0)
            except Exception:
                pass
