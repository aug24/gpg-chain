"""GPG test helper: key generation and payload signing."""


class GPGHelper:
    """Generates ephemeral GPG key pairs and constructs signed payloads for tests."""

    def generate_key(self, uid: str, algorithm: str = "Ed25519") -> dict:
        """Generate a test key pair.

        Returns:
            {
                "fingerprint": str,
                "armored_public": str,
                "armored_private": str,
                "uid": str,
            }
        """
        raise NotImplementedError

    def sign_submit_payload(self, armored_public: str, armored_private: str,
                            fingerprint: str, timestamp: int) -> str:
        """Sign the SUBMIT payload. Returns base64-encoded detached sig."""
        raise NotImplementedError

    def sign_trust_payload(self, block_hash: str, signer_fingerprint: str,
                           timestamp: int, armored_private: str) -> str:
        """Sign the TRUST payload. Returns base64-encoded detached sig."""
        raise NotImplementedError

    def sign_revoke_payload(self, fingerprint: str, block_hash: str,
                            armored_private: str) -> str:
        """Sign the REVOKE payload. Returns base64-encoded detached sig."""
        raise NotImplementedError
