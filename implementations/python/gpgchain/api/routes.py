"""API route definitions. All routes return 501 until implemented."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse


NOT_IMPLEMENTED = JSONResponse({"error": "not implemented"}, status_code=501)


def register_routes(app: FastAPI) -> None:

    # --- Public endpoints ---

    @app.get("/blocks")
    async def get_blocks():
        return NOT_IMPLEMENTED

    @app.get("/block/{fingerprint}")
    async def get_block(fingerprint: str):
        return NOT_IMPLEMENTED

    @app.post("/block", status_code=201)
    async def add_block():
        return NOT_IMPLEMENTED

    @app.post("/block/{fingerprint}/sign")
    async def sign_block(fingerprint: str):
        return NOT_IMPLEMENTED

    @app.post("/block/{fingerprint}/revoke")
    async def revoke_block(fingerprint: str):
        return NOT_IMPLEMENTED

    @app.get("/search")
    async def search(q: str = ""):
        return NOT_IMPLEMENTED

    @app.get("/.well-known/gpgchain.json")
    async def well_known():
        return NOT_IMPLEMENTED

    # --- Peer endpoints ---

    @app.get("/peers")
    async def get_peers():
        return NOT_IMPLEMENTED

    @app.post("/peers")
    async def add_peer():
        return NOT_IMPLEMENTED

    @app.get("/p2p/hashes")
    async def get_hashes():
        return NOT_IMPLEMENTED

    @app.get("/p2p/block/{block_hash}")
    async def get_block_by_hash(block_hash: str):
        return NOT_IMPLEMENTED

    @app.post("/p2p/block")
    async def receive_block():
        return NOT_IMPLEMENTED

    @app.post("/p2p/sign")
    async def receive_sig():
        return NOT_IMPLEMENTED

    @app.post("/p2p/revoke")
    async def receive_revoke():
        return NOT_IMPLEMENTED
