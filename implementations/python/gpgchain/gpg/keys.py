"""GPG key parsing and validation."""


def parse_armored_key(armored: str) -> tuple[str, list[str]]:
    """Parse an ASCII-armored public key.

    Returns:
        (fingerprint, uids) where fingerprint is uppercase hex, no spaces.

    Raises:
        ValueError: if the key cannot be parsed or fails minimum strength requirements.
    """
    raise NotImplementedError


def check_key_strength(armored: str) -> None:
    """Raise ValueError if the key does not meet minimum strength requirements.

    Rules:
        - RSA: minimum 2048 bits
        - DSA-1024: always rejected
        - Ed25519: always accepted
    """
    raise NotImplementedError


def extract_email_domains(uids: list[str]) -> list[str]:
    """Extract email domains from a list of UID strings.

    Returns list of lowercase domain strings (e.g. ['example.com']).
    Returns empty list if no email UIDs are present.
    """
    raise NotImplementedError
