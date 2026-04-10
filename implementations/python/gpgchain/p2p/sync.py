"""Sync-on-connect and periodic cross-validation."""
import logging

import httpx

from gpgchain.chain.hashing import compute_block_hash, compute_sig_entry_hash
from gpgchain.chain.models import Block, SigEntry
from gpgchain.gpg.keys import parse_armored_key, check_key_strength, extract_email_domains
from gpgchain.gpg.payloads import submit_payload, trust_payload
from gpgchain.gpg.verify import verify_detached_sig

log = logging.getLogger(__name__)


class Sync:

    def __init__(self, store, peers: list, domains: list = None, allow_all: bool = True):
        self._store = store
        self._peers = peers        # direct reference to app.state.peer_list
        self._domains = domains or []
        self._allow_all = allow_all

    def sync_with_peer(self, peer_url: str) -> None:
        """Fetch /p2p/hashes from peer, request and verify missing blocks."""
        base = peer_url.rstrip("/")
        try:
            resp = httpx.get(f"{base}/p2p/hashes", timeout=10.0)
            if resp.status_code != 200:
                return
            peer_hashes: dict[str, str] = resp.json()
        except Exception as exc:
            log.warning("sync_with_peer: failed to fetch hashes from %s: %s", peer_url, exc)
            return

        local_hashes = self._store.hashes()

        # Step 3a — blocks peer has that we don't
        for fingerprint, peer_head in peer_hashes.items():
            if fingerprint not in local_hashes:
                self._fetch_and_store_block(base, fingerprint)
            elif local_hashes[fingerprint] != peer_head:
                # Step 3b — sig chain head differs; fetch missing sigs
                self._sync_sig_chain(base, fingerprint)

        # Step 4 — push our blocks that peer is missing
        for fingerprint in local_hashes:
            if fingerprint not in peer_hashes:
                block = self._store.get(fingerprint)
                if block is not None:
                    self._push_block_to_peer(base, block)

    def _fetch_and_store_block(self, base_url: str, fingerprint: str) -> None:
        try:
            resp = httpx.get(f"{base_url}/block/{fingerprint}", timeout=10.0)
            if resp.status_code != 200:
                return
            data = resp.json()
        except Exception:
            return
        self._validate_and_store(data)

    def _push_block_to_peer(self, base_url: str, block: Block) -> None:
        from gpgchain.p2p.gossip import block_to_dict
        try:
            httpx.post(
                f"{base_url}/p2p/block",
                json={"block": block_to_dict(block)},
                timeout=5.0,
            )
        except Exception:
            pass

    def _validate_and_store(self, data: dict) -> None:
        """Validate a block dict received from a peer and store it if valid."""
        armored_key = data.get("armored_key", "")
        self_sig = data.get("self_sig", "")
        submit_ts = data.get("submit_timestamp", 0)

        try:
            fp, uids = parse_armored_key(armored_key)
            check_key_strength(armored_key)
        except ValueError:
            return

        if not self._allow_all:
            key_domains = extract_email_domains(uids)
            if not key_domains or not any(d in self._domains for d in key_domains):
                return

        payload = submit_payload(fp, armored_key, submit_ts)
        if not verify_detached_sig(payload, self_sig, armored_key):
            return

        if self._store.get(fp) is not None:
            return

        block = Block(
            hash=compute_block_hash(fp, armored_key, self_sig),
            fingerprint=fp,
            armored_key=armored_key,
            uids=uids,
            submit_timestamp=submit_ts,
            self_sig=self_sig,
        )
        try:
            self._store.add(block)
        except ValueError:
            return  # added concurrently

        sig_chain = data.get("sig_chain", [])
        if sig_chain:
            self._apply_sig_entries(fp, sig_chain)

    def _sync_sig_chain(self, base_url: str, fingerprint: str) -> None:
        try:
            resp = httpx.get(f"{base_url}/block/{fingerprint}", timeout=10.0)
            if resp.status_code != 200:
                return
            data = resp.json()
        except Exception:
            return
        self._apply_sig_entries(fingerprint, data.get("sig_chain", []))

    def _apply_sig_entries(self, fingerprint: str, sig_entries: list) -> None:
        """Apply missing sig entries from peer data to local store."""
        block = self._store.get(fingerprint)
        if block is None:
            return

        existing_sigs = {e.signer_fingerprint for e in block.sig_entries}

        for entry_data in sig_entries:
            signer_fp = entry_data.get("signer_fingerprint", "")
            if signer_fp in existing_sigs:
                continue

            sig = entry_data.get("sig", "")
            ts = entry_data.get("timestamp", 0)
            prev_hash = entry_data.get("prev_hash", "")
            claimed_hash = entry_data.get("hash", "")
            signer_armored_key = entry_data.get("signer_armored_key", "") or ""
            source_node = entry_data.get("source_node", "") or ""

            if signer_armored_key:
                signer_key = signer_armored_key
            else:
                signer_block = self._store.get(signer_fp)
                if signer_block is None:
                    continue
                signer_key = signer_block.armored_key

            payload = trust_payload(block.hash, signer_fp, ts)
            if not verify_detached_sig(payload, sig, signer_key):
                continue

            computed_hash = compute_sig_entry_hash(prev_hash, signer_fp, sig, ts)
            if claimed_hash and claimed_hash != computed_hash:
                continue

            entry = SigEntry(
                hash=computed_hash,
                prev_hash=prev_hash,
                signer_fingerprint=signer_fp,
                sig=sig,
                timestamp=ts,
                signer_armored_key=signer_armored_key,
                source_node=source_node,
            )
            try:
                self._store.add_sig(fingerprint, entry)
                existing_sigs.add(signer_fp)
                # Refresh block to reflect updated sig chain for next iteration
                block = self._store.get(fingerprint)
                if block is None:
                    break
            except Exception:
                pass

    def cross_validate(self) -> list[str]:
        """Compare {fp: sig_chain_head} across all peers.

        Returns list of fingerprints where peers disagree.
        """
        local_hashes = self._store.hashes()
        mismatches: list[str] = []

        for peer_url in list(self._peers):
            base = peer_url.rstrip("/")
            try:
                resp = httpx.get(f"{base}/p2p/hashes", timeout=5.0)
                if resp.status_code != 200:
                    continue
                peer_hashes: dict[str, str] = resp.json()
            except Exception:
                continue

            for fp, local_head in local_hashes.items():
                peer_head = peer_hashes.get(fp)
                if peer_head is not None and peer_head != local_head:
                    log.warning(
                        "cross_validate: sig_chain_head mismatch fp=%s "
                        "local=%s peer(%s)=%s",
                        fp, local_head, peer_url, peer_head,
                    )
                    if fp not in mismatches:
                        mismatches.append(fp)
                elif fp not in peer_hashes:
                    log.warning(
                        "cross_validate: peer %s is missing block %s",
                        peer_url, fp,
                    )

        return mismatches
