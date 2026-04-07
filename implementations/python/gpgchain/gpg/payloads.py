"""Typed binary signing payload construction.

All payloads use null byte (0x00) as separator.
All hex values are uppercase, no spaces.
Timestamps are decimal ASCII unix seconds.
"""
import hashlib


def submit_payload(fingerprint: str, armored_key: str, timestamp: int) -> bytes:
    """GPGCHAIN_SUBMIT_V1\\x00<fingerprint>\\x00<sha256_of_armored_key>\\x00<timestamp>"""
    raise NotImplementedError


def trust_payload(block_hash: str, signer_fingerprint: str, timestamp: int) -> bytes:
    """GPGCHAIN_TRUST_V1\\x00<block_hash>\\x00<signer_fingerprint>\\x00<timestamp>"""
    raise NotImplementedError


def revoke_payload(fingerprint: str, block_hash: str) -> bytes:
    """GPGCHAIN_REVOKE_V1\\x00<fingerprint>\\x00<block_hash>"""
    raise NotImplementedError
