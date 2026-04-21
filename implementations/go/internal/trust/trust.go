// Package trust implements client-side trust graph evaluation.
// Trust decisions are always made by the client. This package never contacts
// a server to make a trust decision.
package trust

import (
	"sort"

	"github.com/aug24/gpg-chain/internal/chain"
)

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

// DisjointScore returns the maximum number of vertex-disjoint trust paths from
// rootFP to targetFP within maxDepth hops.
//
// Paths are vertex-disjoint when they share no intermediate key: a score of N
// means no single intermediate key compromise can reduce the count by more than 1.
//
// Implemented as max-flow on a node-split graph where each intermediate node has
// internal capacity 1.
func DisjointScore(g Graph, targetFP, rootFP string, maxDepth int) int {
	if rootFP == targetFP {
		return 1
	}
	return disjointMaxFlow(g, targetFP, rootFP, maxDepth)
}

// DisjointIsTrusted returns true if DisjointScore >= threshold.
func DisjointIsTrusted(g Graph, targetFP, rootFP string, maxDepth, threshold int) bool {
	return DisjointScore(g, targetFP, rootFP, maxDepth) >= threshold
}

func disjointMaxFlow(g Graph, targetFP, rootFP string, maxDepth int) int {
	// Forward BFS: minimum distance from root to each node.
	distFwd := map[string]int{rootFP: 0}
	queue := []string{rootFP}
	for len(queue) > 0 {
		fp := queue[0]
		queue = queue[1:]
		d := distFwd[fp]
		if d >= maxDepth {
			continue
		}
		// g[fp] = set of signers of fp; we need what fp has signed.
		// We build the forward signed map below; here we just BFS all reachable nodes
		// using the reverse direction first to determine distances.
		// Actually we need the forward map: build it lazily below.
		// For the forward BFS we need "what has fp signed", i.e. fp appears as a signer.
		// We'll rebuild the signed map after this loop.
		_ = d
	}

	// Build forward signing map: signed[signer] = list of targets signer has signed.
	signed := map[string][]string{}
	for fp, signers := range g {
		for signer := range signers {
			signed[signer] = append(signed[signer], fp)
		}
	}

	// Redo forward BFS using the signing-forward map.
	distFwd = map[string]int{rootFP: 0}
	queue = []string{rootFP}
	for len(queue) > 0 {
		fp := queue[0]
		queue = queue[1:]
		d := distFwd[fp]
		if d >= maxDepth {
			continue
		}
		for _, target := range signed[fp] {
			if _, seen := distFwd[target]; !seen {
				distFwd[target] = d + 1
				queue = append(queue, target)
			}
		}
	}
	if _, ok := distFwd[targetFP]; !ok {
		return 0
	}

	// Build reverse graph for backward BFS: rev[fp] = set of nodes that fp points to
	// in the forward direction (i.e. nodes fp has signed). Since g[fp][signer] means
	// signer signed fp, the reverse for backward BFS from target is: for each fp that
	// was signed by someone, that someone is reachable backward from fp.
	// In other words: distBwd[fp] = min hops from fp to target in forward graph.
	// For backward BFS we traverse the forward-signing edges in reverse:
	// if fp signed target2, then from target2 we can reach fp in reverse.
	// So rev2[target2] contains fp (fp signed target2).
	rev2 := map[string][]string{}
	for signer, targets := range signed {
		for _, tgt := range targets {
			rev2[tgt] = append(rev2[tgt], signer)
		}
	}

	// Backward BFS: minimum distance from each node back to targetFP.
	distBwd := map[string]int{targetFP: 0}
	queue = []string{targetFP}
	for len(queue) > 0 {
		fp := queue[0]
		queue = queue[1:]
		d := distBwd[fp]
		for _, nbr := range rev2[fp] {
			if _, seen := distBwd[nbr]; !seen {
				distBwd[nbr] = d + 1
				queue = append(queue, nbr)
			}
		}
	}

	// Collect intermediate nodes on valid depth-bounded paths.
	var intermediates []string
	for fp, d1 := range distFwd {
		if fp == rootFP || fp == targetFP {
			continue
		}
		d2, ok := distBwd[fp]
		if ok && d1+d2 <= maxDepth {
			intermediates = append(intermediates, fp)
		}
	}
	sort.Strings(intermediates)

	// Assign node IDs: 0=source, 1=sink, 2+2i=in-node, 2+2i+1=out-node.
	interIdx := map[string]int{}
	for i, fp := range intermediates {
		interIdx[fp] = i
	}
	total := 2 + 2*len(intermediates)
	const SOURCE, SINK = 0, 1

	inID := func(fp string) int { return 2 + 2*interIdx[fp] }
	outID := func(fp string) int { return 2 + 2*interIdx[fp] + 1 }

	// Flow network adjacency list.
	type edge struct{ to, cap, rev int }
	net := make([][]edge, total)
	addEdge := func(u, v, cap int) {
		net[u] = append(net[u], edge{v, cap, len(net[v])})
		net[v] = append(net[v], edge{u, 0, len(net[u]) - 1})
	}

	// Internal split edges (vertex-disjointness constraint).
	for _, fp := range intermediates {
		addEdge(inID(fp), outID(fp), 1)
	}

	// Cross edges filtered to depth-bounded paths.
	inf := len(intermediates) + 2
	sources := append([]string{rootFP}, intermediates...)
	for _, fp1 := range sources {
		d1 := distFwd[fp1]
		var u int
		if fp1 == rootFP {
			u = SOURCE
		} else {
			u = outID(fp1)
		}
		for _, fp2 := range signed[fp1] {
			d2, ok := distBwd[fp2]
			if !ok {
				continue
			}
			if d1+1+d2 > maxDepth {
				continue
			}
			var v int
			if fp2 == targetFP {
				v = SINK
			} else if _, ok := interIdx[fp2]; ok {
				v = inID(fp2)
			} else {
				continue
			}
			addEdge(u, v, inf)
		}
	}

	// Edmonds-Karp max-flow.
	totalFlow := 0
	for {
		prev := make([]struct{ node, edge int }, total)
		for i := range prev {
			prev[i].node = -1
		}
		prev[SOURCE] = struct{ node, edge int }{SOURCE, -1}
		bfsQ := []int{SOURCE}
		for len(bfsQ) > 0 && prev[SINK].node == -1 {
			u := bfsQ[0]
			bfsQ = bfsQ[1:]
			for i, e := range net[u] {
				if prev[e.to].node == -1 && e.cap > 0 {
					prev[e.to] = struct{ node, edge int }{u, i}
					bfsQ = append(bfsQ, e.to)
				}
			}
		}
		if prev[SINK].node == -1 {
			break
		}
		// Bottleneck.
		bn := 1 << 30
		for v := SINK; v != SOURCE; {
			p := prev[v]
			if net[p.node][p.edge].cap < bn {
				bn = net[p.node][p.edge].cap
			}
			v = p.node
		}
		// Update residual.
		for v := SINK; v != SOURCE; {
			p := prev[v]
			net[p.node][p.edge].cap -= bn
			net[v][net[p.node][p.edge].rev].cap += bn
			v = p.node
		}
		totalFlow += bn
	}
	return totalFlow
}
