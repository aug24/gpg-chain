"""API route definitions."""
import ipaddress
import socket
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from gpgchain.chain.models import Block, SigEntry
from gpgchain.chain.hashing import compute_block_hash, compute_sig_entry_hash
from gpgchain.gpg.keys import parse_armored_key, check_key_strength, extract_email_domains
from gpgchain.gpg.payloads import submit_payload, trust_payload, revoke_payload
from gpgchain.gpg.verify import verify_detached_sig

MAX_PEERS = 50


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _sig_entry_to_dict(entry: SigEntry) -> dict:
    d: dict[str, Any] = {
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


def _block_to_dict(block: Block) -> dict:
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


def _err(msg: str, status: int) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_routes(app: FastAPI) -> None:

    # --- Public endpoints ---

    @app.get("/blocks")
    async def get_blocks(request: Request):
        store = request.app.state.store
        blocks = store.all()
        return JSONResponse([_block_to_dict(b) for b in blocks])

    @app.get("/block/{fingerprint}")
    async def get_block(fingerprint: str, request: Request):
        store = request.app.state.store
        block = store.get(fingerprint)
        if block is None:
            return _err("block not found", 404)
        return JSONResponse(_block_to_dict(block))

    @app.post("/block", status_code=201)
    async def add_block(request: Request, background_tasks: BackgroundTasks):
        store = request.app.state.store
        domains: list[str] = request.app.state.domains
        allow_all_domains: bool = request.app.state.allow_all_domains

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        armored_key: str = body.get("armored_key", "")
        self_sig: str = body.get("self_sig", "")
        submit_ts: int | None = body.get("submit_timestamp")

        if not armored_key or not self_sig:
            return _err("armored_key and self_sig are required", 400)

        try:
            fingerprint, uids = parse_armored_key(armored_key)
        except ValueError as exc:
            return _err(f"invalid armored key: {exc}", 400)

        try:
            check_key_strength(armored_key)
        except ValueError as exc:
            return _err(f"key too weak: {exc}", 400)

        key_domains = extract_email_domains(uids)
        if not key_domains:
            return _err("key has no email UID", 400)
        if not allow_all_domains:
            if not any(d in domains for d in key_domains):
                return _err("key domain not in allowlist", 403)

        block_hash = compute_block_hash(fingerprint, armored_key, self_sig)

        ts = submit_ts if submit_ts is not None else int(time.time())
        payload = submit_payload(fingerprint, armored_key, ts)
        if not verify_detached_sig(payload, self_sig, armored_key):
            return _err("self_sig verification failed", 400)

        if store.get(fingerprint) is not None:
            return _err("block already exists for this fingerprint", 409)

        block = Block(
            hash=block_hash,
            fingerprint=fingerprint,
            armored_key=armored_key,
            uids=uids,
            submit_timestamp=ts,
            self_sig=self_sig,
        )
        store.add(block)

        background_tasks.add_task(
            request.app.state.gossip.gossip_block, block
        )

        return JSONResponse(_block_to_dict(block), status_code=201)

    @app.post("/block/{fingerprint}/sign")
    async def sign_block(fingerprint: str, request: Request, background_tasks: BackgroundTasks):
        store = request.app.state.store

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        signer_fp: str = body.get("signer_fingerprint", "")
        sig: str = body.get("sig", "")
        timestamp: int | None = body.get("timestamp")
        signer_armored_key: str = body.get("signer_armored_key", "") or ""
        source_node: str = body.get("source_node", "") or ""

        if not signer_fp or not sig:
            return _err("signer_fingerprint and sig are required", 400)

        ts = timestamp if timestamp is not None else int(time.time())

        block = store.get(fingerprint)
        if block is None:
            return _err("block not found", 404)

        if block.revoked:
            return _err("block is revoked", 409)

        if signer_armored_key:
            try:
                check_key_strength(signer_armored_key)
            except ValueError as exc:
                return _err(f"signer key too weak: {exc}", 400)
            signer_key = signer_armored_key
        else:
            signer_block = store.get(signer_fp)
            if signer_block is None:
                return _err("signer block not found on ledger", 400)
            signer_key = signer_block.armored_key

        payload = trust_payload(block.hash, signer_fp, ts)
        if not verify_detached_sig(payload, sig, signer_key):
            return _err("sig verification failed", 400)

        for existing in block.sig_entries:
            if existing.signer_fingerprint == signer_fp:
                return _err("signer has already signed this block", 409)

        prev_hash = block.sig_chain_head if block.sig_chain_head else block.hash
        entry_hash = compute_sig_entry_hash(prev_hash, signer_fp, sig, ts)

        entry = SigEntry(
            hash=entry_hash,
            prev_hash=prev_hash,
            signer_fingerprint=signer_fp,
            sig=sig,
            timestamp=ts,
            signer_armored_key=signer_armored_key,
            source_node=source_node,
        )
        store.add_sig(fingerprint, entry)

        background_tasks.add_task(
            request.app.state.gossip.gossip_sig, fingerprint, entry
        )

        updated_block = store.get(fingerprint)
        return JSONResponse(_block_to_dict(updated_block))

    @app.post("/block/{fingerprint}/revoke")
    async def revoke_block(fingerprint: str, request: Request, background_tasks: BackgroundTasks):
        store = request.app.state.store

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        sig: str = body.get("sig", "")
        if not sig:
            return _err("sig is required", 400)

        block = store.get(fingerprint)
        if block is None:
            return _err("block not found", 404)

        if block.revoked:
            return _err("block is already revoked", 409)

        payload = revoke_payload(fingerprint, block.hash)
        if not verify_detached_sig(payload, sig, block.armored_key):
            return _err("revocation sig verification failed", 403)

        store.revoke(fingerprint, sig)

        background_tasks.add_task(
            request.app.state.gossip.gossip_revoke, fingerprint, sig
        )

        updated_block = store.get(fingerprint)
        return JSONResponse(_block_to_dict(updated_block))

    @app.get("/search")
    async def search(q: str, request: Request):
        store = request.app.state.store
        q_lower = q.lower()
        results = []
        for block in store.all():
            if any(q_lower in uid.lower() for uid in block.uids):
                results.append(_block_to_dict(block))
        return JSONResponse(results)

    @app.get("/.well-known/gpgchain.json")
    async def well_known(request: Request):
        state = request.app.state
        return JSONResponse({
            "node_url": state.node_url,
            "domains": state.domains,
            "peers": state.peer_list,
        })

    # --- Peer endpoints ---

    @app.get("/peers")
    async def get_peers(request: Request):
        return JSONResponse(request.app.state.peer_list)

    @app.post("/peers")
    async def add_peer(request: Request, background_tasks: BackgroundTasks):
        state = request.app.state

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        addr: str = body.get("addr", "")
        if not addr:
            return _err("addr is required", 400)

        try:
            parsed = urlparse(addr)
        except Exception:
            return _err("invalid URL", 400)

        if parsed.scheme not in ("http", "https"):
            return _err("URL scheme must be http or https", 400)

        # Rule 4 — capacity check before expensive DNS + reachability
        if len(state.peer_list) >= MAX_PEERS and addr not in state.peer_list:
            return _err("peer list is at capacity", 429)

        # Rule 2 — reject loopback always; reject private only if allow_private_peers is off
        try:
            host = parsed.hostname or ""
            addr_info = socket.getaddrinfo(host, None)
            for info in addr_info:
                ip = ipaddress.ip_address(info[4][0])
                # Loopback means the peer is this node itself — always reject.
                if ip.is_loopback:
                    return _err("loopback addresses are not allowed", 400)
                if not state.allow_private_peers and (ip.is_private or ip.is_link_local):
                    return _err("private or loopback addresses are not allowed", 400)
        except Exception:
            return _err("could not resolve peer address", 400)

        # Rule 3 — reciprocal reachability check
        try:
            r = httpx.get(f"{addr.rstrip('/')}/peers", timeout=5.0)
            if r.status_code != 200:
                return _err("peer reachability check failed", 400)
        except Exception:
            return _err("peer is not reachable", 400)

        # Rule 5 — silently accept duplicates
        if addr not in state.peer_list:
            state.peer_list.append(addr)

        # Reciprocal registration + sync in the background
        if state.node_url:
            background_tasks.add_task(_register_self_with_peer, addr, state.node_url)
        background_tasks.add_task(state.sync.sync_with_peer, addr)

        return JSONResponse({"ok": True})

    # --- P2P endpoints ---

    @app.get("/p2p/hashes")
    async def get_hashes(request: Request):
        return JSONResponse(request.app.state.store.hashes())

    @app.get("/p2p/block/{block_hash}")
    async def get_block_by_hash(block_hash: str, request: Request):
        store = request.app.state.store
        for block in store.all():
            if block.hash == block_hash:
                return JSONResponse(_block_to_dict(block))
        return _err("block not found", 404)

    @app.post("/p2p/block")
    async def receive_block(request: Request, background_tasks: BackgroundTasks):
        store = request.app.state.store
        domains: list[str] = request.app.state.domains
        allow_all_domains: bool = request.app.state.allow_all_domains

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        block_data = body.get("block")
        if not block_data:
            return _err("block is required", 400)

        armored_key: str = block_data.get("armored_key", "")
        self_sig: str = block_data.get("self_sig", "")
        claimed_hash: str = block_data.get("hash", "")
        submit_ts: int | None = block_data.get("submit_timestamp")

        if not armored_key or not self_sig:
            return _err("block.armored_key and block.self_sig are required", 400)

        try:
            fingerprint, uids = parse_armored_key(armored_key)
        except ValueError as exc:
            return _err(f"invalid armored key: {exc}", 400)

        try:
            check_key_strength(armored_key)
        except ValueError as exc:
            return _err(f"key too weak: {exc}", 400)

        if not allow_all_domains:
            key_domains = extract_email_domains(uids)
            if not key_domains or not any(d in domains for d in key_domains):
                return _err("key domain not in allowlist", 400)

        block_hash = compute_block_hash(fingerprint, armored_key, self_sig)
        if claimed_hash and claimed_hash != block_hash:
            return _err("block hash mismatch", 400)

        ts = submit_ts if submit_ts is not None else int(time.time())
        payload = submit_payload(fingerprint, armored_key, ts)
        if not verify_detached_sig(payload, self_sig, armored_key):
            return _err("self_sig verification failed", 400)

        # Already known
        if store.get(fingerprint) is not None:
            return JSONResponse({"ok": True})

        block = Block(
            hash=block_hash,
            fingerprint=fingerprint,
            armored_key=armored_key,
            uids=uids,
            submit_timestamp=ts,
            self_sig=self_sig,
        )
        store.add(block)

        background_tasks.add_task(
            request.app.state.gossip.gossip_block, block
        )

        return JSONResponse({"ok": True})

    @app.post("/p2p/sign")
    async def receive_sig(request: Request, background_tasks: BackgroundTasks):
        store = request.app.state.store

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        fingerprint: str = body.get("fingerprint", "")
        entry_data = body.get("entry")
        if not fingerprint or not entry_data:
            return _err("fingerprint and entry are required", 400)

        signer_fp: str = entry_data.get("signer_fingerprint", "")
        sig: str = entry_data.get("sig", "")
        ts: int = entry_data.get("timestamp", 0)
        prev_hash: str = entry_data.get("prev_hash", "")
        claimed_hash: str = entry_data.get("hash", "")
        signer_armored_key: str = entry_data.get("signer_armored_key", "") or ""
        source_node: str = entry_data.get("source_node", "") or ""

        if not all([signer_fp, sig, prev_hash]):
            return _err("entry.signer_fingerprint, entry.sig, and entry.prev_hash are required", 400)

        block = store.get(fingerprint)
        if block is None:
            return _err("target block not found", 400)

        if block.revoked:
            return _err("block is revoked", 400)

        if signer_armored_key:
            signer_key = signer_armored_key
        else:
            signer_block = store.get(signer_fp)
            if signer_block is None:
                return _err("signer block not found on ledger", 400)
            signer_key = signer_block.armored_key

        payload = trust_payload(block.hash, signer_fp, ts)
        if not verify_detached_sig(payload, sig, signer_key):
            return _err("sig verification failed", 400)

        # Already known
        for existing in block.sig_entries:
            if existing.signer_fingerprint == signer_fp:
                return JSONResponse({"ok": True})

        computed_hash = compute_sig_entry_hash(prev_hash, signer_fp, sig, ts)
        if claimed_hash and claimed_hash != computed_hash:
            return _err("SigEntry hash mismatch", 400)

        entry = SigEntry(
            hash=computed_hash,
            prev_hash=prev_hash,
            signer_fingerprint=signer_fp,
            sig=sig,
            timestamp=ts,
            signer_armored_key=signer_armored_key,
            source_node=source_node,
        )
        store.add_sig(fingerprint, entry)

        background_tasks.add_task(
            request.app.state.gossip.gossip_sig, fingerprint, entry
        )

        return JSONResponse({"ok": True})

    @app.post("/p2p/revoke")
    async def receive_revoke(request: Request, background_tasks: BackgroundTasks):
        store = request.app.state.store

        try:
            body = await request.json()
        except Exception:
            return _err("invalid JSON body", 400)

        fingerprint: str = body.get("fingerprint", "")
        revocation_sig: str = body.get("revocation_sig", "")

        if not fingerprint or not revocation_sig:
            return _err("fingerprint and revocation_sig are required", 400)

        block = store.get(fingerprint)
        if block is None:
            return _err("block not found", 400)

        # Already revoked
        if block.revoked:
            return JSONResponse({"ok": True})

        payload = revoke_payload(fingerprint, block.hash)
        if not verify_detached_sig(payload, revocation_sig, block.armored_key):
            return _err("revocation sig verification failed", 400)

        store.revoke(fingerprint, revocation_sig)

        background_tasks.add_task(
            request.app.state.gossip.gossip_revoke, fingerprint, revocation_sig
        )

        return JSONResponse({"ok": True})


def _register_self_with_peer(peer_url: str, my_node_url: str) -> None:
    """Non-fatal: register this node's URL with the given peer."""
    try:
        httpx.post(
            f"{peer_url.rstrip('/')}/peers",
            json={"addr": my_node_url},
            timeout=5.0,
        )
    except Exception:
        pass
