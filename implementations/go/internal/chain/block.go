// Package chain defines the Block and SigEntry types and their hash computation.
package chain

// SigEntry is one trust signature in a block's linked signature chain.
type SigEntry struct {
	Hash              string `json:"hash"`               // SHA-256 of (PrevHash|SignerFingerprint|Sig|Timestamp)
	PrevHash          string `json:"prev_hash"`          // previous SigEntry hash, or block Hash if first
	SignerFingerprint string `json:"signer_fingerprint"`
	Sig               string `json:"sig"`                // base64 detached GPG sig over TRUST payload
	Timestamp         int64  `json:"timestamp"`          // unix seconds, set by client, authenticated via Sig
	SignerArmoredKey  string `json:"signer_armored_key,omitempty"` // off-ledger only
	SourceNode        string `json:"source_node,omitempty"`        // off-ledger only
}

// Block is a single entry in the ledger.
type Block struct {
	Hash            string     `json:"hash"`             // SHA-256 of (Fingerprint|ArmoredKey|SelfSig)
	Fingerprint     string     `json:"fingerprint"`      // uppercase hex, no spaces
	ArmoredKey      string     `json:"armored_key"`
	UIDs            []string   `json:"uids"`
	SubmitTimestamp int64      `json:"submit_timestamp"`
	SelfSig         string     `json:"self_sig"`
	SigChainHead    string     `json:"sig_chain_head"`
	SigEntries      []SigEntry `json:"sig_entries,omitempty"`
	Revoked         bool       `json:"revoked"`
	RevocationSig   string     `json:"revocation_sig,omitempty"`
}

// ComputeBlockHash returns SHA-256 of (fingerprint | armoredKey | selfSig) as uppercase hex.
func ComputeBlockHash(fingerprint, armoredKey, selfSig string) (string, error) {
	panic("not implemented")
}

// ComputeSigEntryHash returns SHA-256 of (prevHash | signerFP | sig | timestamp) as uppercase hex.
func ComputeSigEntryHash(prevHash, signerFP, sig string, timestamp int64) (string, error) {
	panic("not implemented")
}

// VerifyBlockHash returns true if block.Hash matches the computed hash.
func VerifyBlockHash(b *Block) bool {
	panic("not implemented")
}

// VerifySigChain walks the sig chain from SigChainHead back to block Hash.
// Returns true if the chain is intact.
func VerifySigChain(b *Block) bool {
	panic("not implemented")
}
