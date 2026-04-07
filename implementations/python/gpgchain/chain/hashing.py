"""Hash computation for Block and SigEntry."""
from gpgchain.chain.models import Block, SigEntry


def compute_block_hash(fingerprint: str, armored_key: str, self_sig: str) -> str:
    """SHA-256 of (fingerprint | armored_key | self_sig). Returns uppercase hex."""
    raise NotImplementedError


def compute_sig_entry_hash(prev_hash: str, signer_fingerprint: str, sig: str, timestamp: int) -> str:
    """SHA-256 of (prev_hash | signer_fingerprint | sig | timestamp). Returns uppercase hex."""
    raise NotImplementedError


def verify_block_hash(block: Block) -> bool:
    """Return True if block.hash matches computed hash of its immutable fields."""
    raise NotImplementedError


def verify_sig_chain(block: Block) -> bool:
    """Walk the sig chain from sig_chain_head back to block hash; return True if intact."""
    raise NotImplementedError
