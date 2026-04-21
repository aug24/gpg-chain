"""GPG signature verification using pgpy (pure Python, no subprocess)."""
import base64
import warnings

import pgpy


def verify_detached_sig(payload: bytes, b64_sig: str, armored_public_key: str) -> bool:
    """Verify a base64-encoded detached GPG signature over payload using the given public key.

    Returns True if valid, False otherwise. Never raises.
    """
    try:
        sig_bytes = base64.b64decode(b64_sig)
    except Exception:
        return False

    try:
        key, _ = pgpy.PGPKey.from_blob(armored_public_key)
        sig = pgpy.PGPSignature.from_blob(sig_bytes)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = key.verify(payload, sig)
        return bool(result)
    except Exception:
        return False
