"""GPG test helper: key generation and payload signing using pgpy (pure Python).

No subprocess calls, no gpg-agent, no temporary directories.
"""
import base64
import warnings

import pgpy
from pgpy.constants import (
    CompressionAlgorithm,
    EllipticCurveOID,
    HashAlgorithm,
    KeyFlags,
    PubKeyAlgorithm,
    SymmetricKeyAlgorithm,
)


def _make_key(uid_str: str, algorithm: str = "Ed25519") -> tuple[pgpy.PGPKey, pgpy.PGPUID]:
    """Create a PGPKey with the given UID and algorithm."""
    name = uid_str
    email = None
    if "<" in uid_str and uid_str.endswith(">"):
        parts = uid_str.rsplit("<", 1)
        name = parts[0].strip()
        email = parts[1].rstrip(">").strip()
    elif "@" in uid_str and " " not in uid_str:
        name = uid_str
        email = uid_str

    if algorithm == "Ed25519":
        key = pgpy.PGPKey.new(PubKeyAlgorithm.EdDSA, EllipticCurveOID.Ed25519)
    elif algorithm.startswith("RSA"):
        bits = int(algorithm[3:]) if len(algorithm) > 3 else 2048
        key = pgpy.PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, bits)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    uid = pgpy.PGPUID.new(name, email=email or "")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        key.add_uid(
            uid,
            usage={KeyFlags.Sign},
            hashes=[HashAlgorithm.SHA256],
            ciphers=[SymmetricKeyAlgorithm.AES256],
            compression=[CompressionAlgorithm.ZLIB],
        )
    return key, uid


class GPGHelper:
    """Generates ephemeral GPG key pairs and constructs signed payloads for tests.

    Pure Python via pgpy — no subprocess calls, no gpg-agent.
    """

    def generate_key(self, uid: str, algorithm: str = "Ed25519") -> dict:
        """Generate a test key pair.

        Returns dict with: fingerprint, armored_public, armored_private, uid.
        """
        key, _ = _make_key(uid, algorithm)
        fingerprint = str(key.fingerprint).upper().replace(" ", "")
        return {
            "fingerprint": fingerprint,
            "armored_public": str(key.pubkey),
            "armored_private": str(key),
            "uid": uid,
            "_pgpkey": key,
        }

    def generate_key_with_two_uids(self, uid1: str, uid2: str) -> dict:
        """Generate a key with two UIDs."""
        key, _ = _make_key(uid1)

        # Parse uid2
        name2 = uid2
        email2 = None
        if "<" in uid2 and uid2.endswith(">"):
            parts = uid2.rsplit("<", 1)
            name2 = parts[0].strip()
            email2 = parts[1].rstrip(">").strip()
        elif "@" in uid2 and " " not in uid2:
            name2 = uid2
            email2 = uid2

        uid2_obj = pgpy.PGPUID.new(name2, email=email2 or "")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            key.add_uid(
                uid2_obj,
                usage={KeyFlags.Sign},
                hashes=[HashAlgorithm.SHA256],
                ciphers=[SymmetricKeyAlgorithm.AES256],
                compression=[CompressionAlgorithm.ZLIB],
            )

        fingerprint = str(key.fingerprint).upper().replace(" ", "")
        return {
            "fingerprint": fingerprint,
            "armored_public": str(key.pubkey),
            "armored_private": str(key),
            "uid": uid1,
            "_pgpkey": key,
        }

    def generate_weak_rsa_key(self, uid: str) -> dict:
        """Generate a weak RSA-1024 key for testing rejection."""
        return self.generate_key(uid, algorithm="RSA1024")

    def _sign(self, payload: bytes, key_dict: dict) -> str:
        """Sign payload with the key in key_dict. Returns base64-encoded detached sig."""
        pgpkey = key_dict.get("_pgpkey")
        if pgpkey is None:
            # Key was loaded from armored string; reconstruct
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pgpkey, _ = pgpy.PGPKey.from_blob(key_dict["armored_private"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sig = pgpkey.sign(payload)
        return base64.b64encode(bytes(sig)).decode()

    def sign_submit_payload(self, armored_public: str, armored_private: str,
                            fingerprint: str, timestamp: int,
                            homedir: str = None, key_dict: dict = None) -> str:
        from gpgchain.gpg.payloads import submit_payload
        payload = submit_payload(fingerprint, armored_public, timestamp)
        if key_dict is None:
            key_dict = {"armored_private": armored_private}
        return self._sign(payload, key_dict)

    def sign_trust_payload(self, block_hash: str, signer_fingerprint: str,
                           timestamp: int, armored_private: str,
                           homedir: str = None, key_dict: dict = None) -> str:
        from gpgchain.gpg.payloads import trust_payload
        payload = trust_payload(block_hash, signer_fingerprint, timestamp)
        if key_dict is None:
            key_dict = {"armored_private": armored_private}
        return self._sign(payload, key_dict)

    def sign_revoke_payload(self, fingerprint: str, block_hash: str,
                            armored_private: str,
                            homedir: str = None, key_dict: dict = None) -> str:
        from gpgchain.gpg.payloads import revoke_payload
        payload = revoke_payload(fingerprint, block_hash)
        if key_dict is None:
            key_dict = {"armored_private": armored_private}
        return self._sign(payload, key_dict)
