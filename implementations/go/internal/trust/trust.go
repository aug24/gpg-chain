// Package trust implements client-side trust graph evaluation.
// Trust decisions are always made by the client. This package never contacts
// a server to make a trust decision.
package trust

import "github.com/aug24/gpg-chain/internal/chain"

// Graph is an adjacency map: fingerprint -> set of fingerprints that signed it.
type Graph map[string]map[string]struct{}

// Build constructs a trust graph from a slice of blocks.
// Revoked keys are included as nodes but their outgoing edges are excluded.
// Signatures from revoked signers are excluded.
func Build(blocks []*chain.Block) Graph {
	panic("not implemented")
}

// Score counts distinct non-revoked trust paths from rootFP to targetFP within maxDepth.
func Score(g Graph, targetFP, rootFP string, maxDepth int) int {
	panic("not implemented")
}

// IsTrusted returns true if Score >= threshold.
func IsTrusted(g Graph, targetFP, rootFP string, maxDepth, threshold int) bool {
	panic("not implemented")
}

// TrustedSet returns all fingerprints reachable from rootFP at or above threshold.
func TrustedSet(g Graph, rootFP string, maxDepth, threshold int) []string {
	panic("not implemented")
}
