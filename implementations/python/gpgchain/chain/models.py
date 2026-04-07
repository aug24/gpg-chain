"""Block and SigEntry dataclasses."""
from dataclasses import dataclass, field


@dataclass
class SigEntry:
    hash: str                        # SHA-256 of (prev_hash | signer_fp | sig | timestamp)
    prev_hash: str                   # previous SigEntry hash, or block hash if first
    signer_fingerprint: str
    sig: str                         # base64 detached GPG sig over TRUST payload
    timestamp: int                   # unix seconds, set by client, authenticated via sig
    signer_armored_key: str = ""     # off-ledger only: inline public key
    source_node: str = ""            # off-ledger only: URL of signer's ledger node


@dataclass
class Block:
    hash: str                        # SHA-256 of (fingerprint | armored_key | self_sig)
    fingerprint: str                 # uppercase hex, no spaces
    armored_key: str                 # ASCII-armored public key
    uids: list[str] = field(default_factory=list)
    submit_timestamp: int = 0        # unix seconds, set by client, authenticated via self_sig
    self_sig: str = ""               # base64 detached GPG sig over SUBMIT payload
    sig_chain_head: str = ""         # hash of most recent SigEntry
    sig_entries: list[SigEntry] = field(default_factory=list)
    revoked: bool = False
    revocation_sig: str = ""         # base64 detached GPG sig over REVOKE payload
