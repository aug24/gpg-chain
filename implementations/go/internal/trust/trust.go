// Package trust implements client-side trust graph evaluation.
// Trust decisions are always made by the client. This package never contacts
// a server to make a trust decision.
package trust

import "github.com/aug24/gpg-chain/internal/chain"

// Graph is an adjacency map: fingerprint -> set of signer fingerprints.
// g[fp] is the set of fingerprints that have signed block fp.
// A revoked key is present as a node but has no outgoing trust paths through it.
type Graph map[string]map[string]struct{}

// Build constructs a trust graph from a slice of blocks.
// Revoked keys are included as nodes but their outgoing trust paths are excluded:
// a revoked signer's signatures do not propagate trust.
func Build(blocks []*chain.Block) Graph {
	revoked := make(map[string]bool)
	for _, b := range blocks {
		if b.Revoked {
			revoked[b.Fingerprint] = true
		}
	}

	g := make(Graph)
	for _, b := range blocks {
		if _, ok := g[b.Fingerprint]; !ok {
			g[b.Fingerprint] = make(map[string]struct{})
		}
		if b.Revoked {
			continue // revoked blocks are dead ends
		}
		for _, e := range b.SigEntries {
			if revoked[e.SignerFingerprint] {
				continue
			}
			g[b.Fingerprint][e.SignerFingerprint] = struct{}{}
		}
	}
	return g
}

// Score counts distinct non-cyclic trust paths from rootFP to targetFP within maxDepth.
func Score(g Graph, targetFP, rootFP string, maxDepth int) int {
	if rootFP == targetFP {
		return 1
	}
	return countPaths(g, targetFP, rootFP, maxDepth)
}

type bfsState struct {
	fp    string
	depth int
	path  map[string]bool
}

func countPaths(g Graph, targetFP, rootFP string, maxDepth int) int {
	count := 0
	queue := []bfsState{{fp: targetFP, depth: 0, path: map[string]bool{targetFP: true}}}

	for len(queue) > 0 {
		cur := queue[0]
		queue = queue[1:]

		if cur.depth >= maxDepth {
			continue
		}

		for signerFP := range g[cur.fp] {
			if cur.path[signerFP] {
				continue // cycle
			}
			if signerFP == rootFP {
				count++
				continue
			}
			newPath := make(map[string]bool, len(cur.path)+1)
			for k, v := range cur.path {
				newPath[k] = v
			}
			newPath[signerFP] = true
			queue = append(queue, bfsState{fp: signerFP, depth: cur.depth + 1, path: newPath})
		}
	}
	return count
}

// IsTrusted returns true if Score >= threshold.
func IsTrusted(g Graph, targetFP, rootFP string, maxDepth, threshold int) bool {
	return Score(g, targetFP, rootFP, maxDepth) >= threshold
}

// TrustedSet returns all fingerprints reachable from rootFP at or above threshold.
func TrustedSet(g Graph, rootFP string, maxDepth, threshold int) []string {
	var result []string
	for fp := range g {
		if fp == rootFP {
			continue
		}
		if IsTrusted(g, fp, rootFP, maxDepth, threshold) {
			result = append(result, fp)
		}
	}
	return result
}
