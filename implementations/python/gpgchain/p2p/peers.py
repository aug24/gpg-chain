"""Peer list management."""
import ipaddress
import re


PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


class PeerList:

    def __init__(self, max_peers: int = 50):
        self._peers: list[str] = []
        self._max = max_peers

    def add(self, url: str) -> None:
        """Add a peer URL after validation. Raise ValueError on failure."""
        raise NotImplementedError

    def remove(self, url: str) -> None:
        raise NotImplementedError

    def all(self) -> list[str]:
        return list(self._peers)

    def is_private_address(self, url: str) -> bool:
        """Return True if the URL resolves to a private or loopback address."""
        raise NotImplementedError

    def is_reachable(self, url: str) -> bool:
        """Perform a reciprocal reachability check (GET /peers). Return True if reachable."""
        raise NotImplementedError
