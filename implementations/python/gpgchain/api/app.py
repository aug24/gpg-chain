"""FastAPI application factory."""
from fastapi import FastAPI


def create_app(
    store_dir: str = "./data",
    store_prefix_len: int = 4,
    cache_size: int = 128,
    peers: list[str] | None = None,
    domains: list[str] | None = None,
    allow_all_domains: bool = False,
    node_url: str = "",
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="GPG Chain", version="0.1.0")

    from gpgchain.api.routes import register_routes
    register_routes(app)

    return app
