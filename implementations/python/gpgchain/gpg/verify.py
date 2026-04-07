"""GPG signature verification."""


def verify_detached_sig(payload: bytes, b64_sig: str, armored_public_key: str) -> bool:
    """Verify a base64-encoded detached GPG signature over payload using the given public key.

    Returns True if valid, False otherwise. Never raises.
    """
    raise NotImplementedError
