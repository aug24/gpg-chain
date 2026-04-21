"""FastAPI application factory."""
import os
from fastapi import FastAPI


def create_app(
    store_dir: str = None,
    store_prefix_len: int = 4,
    cache_size: int = 128,
    peers: list[str] | None = None,
    domains: list[str] | None = None,
    allow_all_domains: bool = None,
    allow_private_peers: bool = None,
    node_url: str = "",
) -> FastAPI:
    # Environment variable overrides
    if store_dir is None:
        store_dir = os.environ.get("GPGCHAIN_STORE_DIR", "./data")
    if allow_all_domains is None:
        allow_all_domains = os.environ.get("GPGCHAIN_ALLOW_ALL", "").lower() in ("1", "true", "yes")
    if allow_private_peers is None:
        allow_private_peers = os.environ.get("GPGCHAIN_ALLOW_PRIVATE_PEERS", "").lower() in ("1", "true", "yes")
    if domains is None:
        env_domains = os.environ.get("GPGCHAIN_DOMAINS", "")
        domains = [d.strip() for d in env_domains.split(",") if d.strip()] if env_domains else []
    if node_url == "":
        node_url = os.environ.get("GPGCHAIN_NODE_URL", "")
    if not peers:
        env_peers = os.environ.get("GPGCHAIN_PEERS", "")
        peers = [p.strip() for p in env_peers.split(",") if p.strip()] if env_peers else []

    from gpgchain.store.dir_store import DirStore
    from gpgchain.p2p.gossip import Gossip
    from gpgchain.p2p.sync import Sync

    app = FastAPI(title="GPG Chain", version="0.1.0")

    peer_list = list(peers) if peers else []

    app.state.store = DirStore(store_dir, prefix_len=store_prefix_len, cache_size=cache_size)
    app.state.domains = list(domains) if domains else []
    app.state.allow_all_domains = allow_all_domains
    app.state.allow_private_peers = allow_private_peers
    app.state.node_url = node_url
    app.state.peer_list = peer_list

    app.state.peer_domains: dict[str, list[str]] = {}  # peer URL → declared domains
    app.state.gossip = Gossip(app.state.peer_list)
    app.state.sync = Sync(
        app.state.store,
        app.state.peer_list,
        domains=app.state.domains,
        allow_all=allow_all_domains,
    )

    from gpgchain.api.routes import register_routes
    register_routes(app)

    if peer_list:
        @app.on_event("startup")
        async def _startup_sync():
            import asyncio
            import threading

            def _sync_all():
                for peer in list(app.state.peer_list):
                    try:
                        app.state.sync.sync_with_peer(peer)
                    except Exception:
                        pass

            threading.Thread(target=_sync_all, daemon=True).start()

    return app
