"""GPG key parsing and validation using pgpy (pure Python, no subprocess)."""
import re
import warnings

import pgpy
from pgpy.constants import PubKeyAlgorithm


def parse_armored_key(armored: str) -> tuple[str, list[str]]:
    """Parse an ASCII-armored public key.

    Returns:
        (fingerprint, uids) where fingerprint is uppercase hex, no spaces.

    Raises:
        ValueError: if the key cannot be parsed or fails minimum strength requirements.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            key, _ = pgpy.PGPKey.from_blob(armored)
    except Exception as exc:
        raise ValueError(f"Failed to parse key: {exc}") from exc

    fingerprint = str(key.fingerprint).upper().replace(" ", "")

    uids = []
    for uid in key.userids:
        if uid.name and uid.email:
            uids.append(f"{uid.name} <{uid.email}>")
        elif uid.email:
            uids.append(uid.email)
        elif uid.name:
            uids.append(uid.name)

    check_key_strength(armored)

    return fingerprint, uids


def check_key_strength(armored: str) -> None:
    """Raise ValueError if the key does not meet minimum strength requirements.

    Rules:
        - RSA: minimum 2048 bits
        - DSA-1024: always rejected
        - Ed25519: always accepted
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            key, _ = pgpy.PGPKey.from_blob(armored)
    except Exception as exc:
        raise ValueError(f"Failed to parse key: {exc}") from exc

    algo = key.key_algorithm
    algo_val = algo.value if hasattr(algo, "value") else int(algo)

    if algo_val == 1:  # RSA
        try:
            bits = key._key.keymaterial.n.bit_length()
        except Exception:
            bits = 0
        if bits < 2048:
            raise ValueError(f"RSA key too weak: {bits} bits (minimum 2048)")
    elif algo_val == 17:  # DSA
        try:
            bits = key._key.keymaterial.p.bit_length()
        except Exception:
            bits = 0
        if bits <= 1024:
            raise ValueError(f"DSA key too weak: {bits} bits (DSA-1024 rejected)")
    # EdDSA (22), ECDSA (19), ECDH (18) are accepted


def extract_email_domains(uids: list[str]) -> list[str]:
    """Extract email domains from a list of UID strings.

    Handles both 'Name <email@domain>' and bare 'email@domain' formats.
    Returns list of lowercase domain strings (e.g. ['example.com']).
    Returns empty list if no email UIDs are present.
    """
    _BRACKETED_RE = re.compile(r"<[^>]+@([^>]+)>")
    _BARE_RE = re.compile(r"^[^@\s]+@([^@\s]+)$")
    domains: set[str] = set()
    for uid in uids:
        match = _BRACKETED_RE.search(uid)
        if match:
            domains.add(match.group(1).lower())
        else:
            match = _BARE_RE.match(uid.strip())
            if match:
                domains.add(match.group(1).lower())
    return sorted(domains)
