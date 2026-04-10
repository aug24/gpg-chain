// Package chain defines the Block and SigEntry types and their hash computation.
package chain

import (
	"crypto/sha256"
	"fmt"
	"strings"
)

// SigEntry is one trust signature in a block's linked signature chain.
type SigEntry struct {
	Hash              string `json:"hash"`
	PrevHash          string `json:"prev_hash"`
	SignerFingerprint string `json:"signer_fingerprint"`
	Sig               string `json:"sig"`
	Timestamp         int64  `json:"timestamp"`
	SignerArmoredKey  string `json:"signer_armored_key,omitempty"`
	SourceNode        string `json:"source_node,omitempty"`
}

// Block is a single entry in the ledger.
type Block struct {
	Hash            string      `json:"hash"`
	Fingerprint     string      `json:"fingerprint"`
	ArmoredKey      string      `json:"armored_key"`
	UIDs            []string    `json:"uids"`
	SubmitTimestamp int64       `json:"submit_timestamp"`
	SelfSig         string      `json:"self_sig"`
	SigChainHead    string      `json:"sig_chain_head"`
	SigEntries      []*SigEntry `json:"sig_chain"`
	Revoked         bool        `json:"revoked"`
	RevocationSig   string      `json:"revocation_sig"`
}

var nullByte = []byte{0x00}

func joinFields(parts ...string) []byte {
	var buf []byte
	for i, p := range parts {
		if i > 0 {
			buf = append(buf, nullByte...)
		}
		buf = append(buf, []byte(p)...)
	}
	return buf
}

func hexSHA256(b []byte) string {
	sum := sha256.Sum256(b)
	return strings.ToUpper(fmt.Sprintf("%x", sum))
}

// ComputeBlockHash returns SHA-256(fingerprint | 0x00 | armoredKey | 0x00 | selfSig)
// as 64 uppercase hex characters.
func ComputeBlockHash(fingerprint, armoredKey, selfSig string) string {
	return hexSHA256(joinFields(fingerprint, armoredKey, selfSig))
}

// ComputeSigEntryHash returns SHA-256(prevHash | 0x00 | signerFP | 0x00 | sig | 0x00 | timestamp)
// as 64 uppercase hex characters.
func ComputeSigEntryHash(prevHash, signerFP, sig string, timestamp int64) string {
	return hexSHA256(joinFields(prevHash, signerFP, sig, fmt.Sprintf("%d", timestamp)))
}
