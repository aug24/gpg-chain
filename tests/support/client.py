"""Thin HTTP client wrapper for behave step definitions."""
import requests


class APIClient:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.last_response = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get_blocks(self):
        self.last_response = requests.get(self._url("/blocks"))
        return self.last_response

    def get_block(self, fingerprint: str):
        self.last_response = requests.get(self._url(f"/block/{fingerprint}"))
        return self.last_response

    def add_block(self, armored_key: str, self_sig: str):
        self.last_response = requests.post(
            self._url("/block"),
            json={"armored_key": armored_key, "self_sig": self_sig},
        )
        return self.last_response

    def sign_block(self, fingerprint: str, signer_fingerprint: str, sig: str,
                   signer_armored_key: str = "", source_node: str = ""):
        body = {"signer_fingerprint": signer_fingerprint, "sig": sig}
        if signer_armored_key:
            body["signer_armored_key"] = signer_armored_key
        if source_node:
            body["source_node"] = source_node
        self.last_response = requests.post(self._url(f"/block/{fingerprint}/sign"), json=body)
        return self.last_response

    def revoke_block(self, fingerprint: str, sig: str):
        self.last_response = requests.post(
            self._url(f"/block/{fingerprint}/revoke"),
            json={"sig": sig},
        )
        return self.last_response

    def search(self, query: str):
        self.last_response = requests.get(self._url("/search"), params={"q": query})
        return self.last_response

    def get_peers(self):
        self.last_response = requests.get(self._url("/peers"))
        return self.last_response

    def add_peer(self, addr: str):
        self.last_response = requests.post(self._url("/peers"), json={"addr": addr})
        return self.last_response

    def get_hashes(self):
        self.last_response = requests.get(self._url("/p2p/hashes"))
        return self.last_response

    def well_known(self):
        self.last_response = requests.get(self._url("/.well-known/gpgchain.json"))
        return self.last_response
