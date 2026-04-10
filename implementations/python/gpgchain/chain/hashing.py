"""Hash computation for Block and SigEntry."""
import hashlib
from gpgchain.chain.models import Block, SigEntry


def compute_block_hash(fingerprint: str, armored_key: str, self_sig: str) -> str:
    """SHA-256 of (fingerprint | armored_key | self_sig). Returns uppercase hex."""
    sep = b"\x00"
    data = (
        fingerprint.encode("utf-8")
        + sep
        + armored_key.encode("utf-8")
        + sep
        + self_sig.encode("utf-8")
    )
    return hashlib.sha256(data).hexdigest().upper()


def compute_sig_entry_hash(prev_hash: str, signer_fingerprint: str, sig: str, timestamp: int) -> str:
    """SHA-256 of (prev_hash | signer_fingerprint | sig | timestamp). Returns uppercase hex."""
    sep = b"\x00"
    data = (
        prev_hash.encode("utf-8")
        + sep
        + signer_fingerprint.encode("utf-8")
        + sep
        + sig.encode("utf-8")
        + sep
        + str(timestamp).encode("utf-8")
    )
    return hashlib.sha256(data).hexdigest().upper()


def verify_block_hash(block: Block) -> bool:
    """Return True if block.hash matches computed hash of its immutable fields."""
    expected = compute_block_hash(block.fingerprint, block.armored_key, block.self_sig)
    return block.hash == expected


def verify_sig_chain(block: Block) -> bool:
    """Walk the sig chain from sig_chain_head back to block hash; return True if intact."""
    if not block.sig_entries:
        return block.sig_chain_head == ""

    # First entry's prev_hash must equal the block hash.
    if block.sig_entries[0].prev_hash != block.hash:
        return False

    for i, entry in enumerate(block.sig_entries):
        # Verify each entry's stored hash matches its computed hash.
        expected = compute_sig_entry_hash(
            entry.prev_hash,
            entry.signer_fingerprint,
            entry.sig,
            entry.timestamp,
        )
        if entry.hash != expected:
            return False

        # Each subsequent entry's prev_hash must equal the preceding entry's hash.
        if i > 0 and entry.prev_hash != block.sig_entries[i - 1].hash:
            return False

    # sig_chain_head must equal the last entry's hash.
    return block.sig_chain_head == block.sig_entries[-1].hash
