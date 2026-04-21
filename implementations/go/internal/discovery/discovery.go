// Package discovery implements client-side BFS key discovery across multiple nodes.
//
// Implements BFS over the peer graph: try each node for the requested key; on
// miss, consult /.well-known/gpgchain.json to learn peers and enqueue them.
//
// When a TrustConfig is supplied, trust is evaluated incrementally as blocks are
// found. The search stops as soon as the threshold is met.
//
// Domain prioritisation ensures domain-specific nodes are tried before allow-all
// nodes, which are tried before unrelated nodes.
package discovery

import (
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/aug24/gpg-chain/internal/chain"
	"github.com/aug24/gpg-chain/internal/trust"
)

// TrustConfig holds trust evaluation parameters.
type TrustConfig struct {
	RootFP    string
	Threshold int
	MaxDepth  int
}

// NodeBlock is a (NodeURL, Block) pair.
type NodeBlock struct {
	NodeURL string
	Block   *chain.Block
}

// BlockResult is the result of a FindBlock search.
type BlockResult struct {
	Found      bool
	NodeURL    string
	Block      *chain.Block
	NodesTried int
	// TrustScore is -1 when no TrustConfig was supplied.
	TrustScore int
	AllCopies  []NodeBlock
}

// EmailResult is the result of a FindBlocksByEmail search.
type EmailResult struct {
	Blocks     []NodeBlock
	NodesTried int
}

// Found returns true when at least one block was located.
func (e *EmailResult) Found() bool { return len(e.Blocks) > 0 }

// ---------------------------------------------------------------------------
// BFS helpers
// ---------------------------------------------------------------------------

type wkResponse struct {
	PeerNodes []struct {
		URL      string   `json:"url"`
		Domains  []string `json:"domains"`
		AllowAll bool     `json:"allow_all"`
	} `json:"peer_nodes"`
	Peers []string `json:"peers"`
}

func fetchWellKnown(client *http.Client, nodeURL string) (wkResponse, error) {
	var wk wkResponse
	resp, err := client.Get(strings.TrimRight(nodeURL, "/") + "/.well-known/gpgchain.json")
	if err != nil {
		return wk, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return wk, nil
	}
	json.NewDecoder(resp.Body).Decode(&wk) //nolint:errcheck
	return wk, nil
}

func fetchBlock(client *http.Client, nodeURL, fingerprint string) (*chain.Block, error) {
	resp, err := client.Get(strings.TrimRight(nodeURL, "/") + "/block/" + fingerprint)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, nil
	}
	var b chain.Block
	if err := json.NewDecoder(resp.Body).Decode(&b); err != nil {
		return nil, err
	}
	return &b, nil
}

func fetchAllBlocks(client *http.Client, nodeURL string) ([]*chain.Block, error) {
	resp, err := client.Get(strings.TrimRight(nodeURL, "/") + "/blocks")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, nil
	}
	var blocks []*chain.Block
	if err := json.NewDecoder(resp.Body).Decode(&blocks); err != nil {
		return nil, err
	}
	return blocks, nil
}

func enqueuePeers(wk wkResponse, targetDomain string, exact, allowAll, normal *[]string, visited map[string]bool) {
	if wk.PeerNodes != nil {
		for _, pn := range wk.PeerNodes {
			u := strings.TrimRight(pn.URL, "/")
			if u == "" || visited[u] {
				continue
			}
			visited[u] = true
			if targetDomain != "" && containsDomain(pn.Domains, targetDomain) {
				*exact = append(*exact, u)
			} else if targetDomain != "" && pn.AllowAll {
				*allowAll = append(*allowAll, u)
			} else {
				*normal = append(*normal, u)
			}
		}
	} else {
		for _, raw := range wk.Peers {
			u := strings.TrimRight(raw, "/")
			if u == "" || visited[u] {
				continue
			}
			visited[u] = true
			*normal = append(*normal, u)
		}
	}
}

func containsDomain(domains []string, target string) bool {
	for _, d := range domains {
		if strings.EqualFold(d, target) {
			return true
		}
	}
	return false
}

func nextNode(exact, allowAll, normal *[]string) string {
	if len(*exact) > 0 {
		v := (*exact)[0]
		*exact = (*exact)[1:]
		return v
	}
	if len(*allowAll) > 0 {
		v := (*allowAll)[0]
		*allowAll = (*allowAll)[1:]
		return v
	}
	v := (*normal)[0]
	*normal = (*normal)[1:]
	return v
}

func hasQueued(exact, allowAll, normal []string) bool {
	return len(exact) > 0 || len(allowAll) > 0 || len(normal) > 0
}

func bestCopy(copies []NodeBlock) NodeBlock {
	best := copies[0]
	for _, nb := range copies[1:] {
		if len(nb.Block.SigEntries) > len(best.Block.SigEntries) {
			best = nb
		}
	}
	return best
}

func blockSlice(m map[string]*chain.Block) []*chain.Block {
	out := make([]*chain.Block, 0, len(m))
	for _, b := range m {
		out = append(out, b)
	}
	return out
}

func domainFromEmail(email string) string {
	if i := strings.LastIndex(email, "@"); i >= 0 {
		return email[i+1:]
	}
	return ""
}

func normaliseURL(raw string) string {
	u := strings.TrimRight(raw, "/")
	if u == "" {
		return ""
	}
	parsed, err := url.Parse(u)
	if err != nil || parsed.Scheme == "" {
		return ""
	}
	return u
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// FindBlock finds a block by fingerprint, fanning out across the peer graph.
//
// When tc is nil, every reachable node is tried (up to maxNodes) and the copy
// with the longest sig chain is returned.
//
// When tc is provided, trust is evaluated after each node that returns the
// target block. The search stops as soon as the score meets tc.Threshold.
func FindBlock(
	fingerprint string,
	seedNodes []string,
	domainHint string,
	maxNodes int,
	timeout time.Duration,
	tc *TrustConfig,
) BlockResult {
	fp := strings.ToUpper(fingerprint)
	client := &http.Client{Timeout: timeout}

	visited := map[string]bool{}
	var exact, allowAll, normal []string
	var copies []NodeBlock
	accumulated := map[string]*chain.Block{}

	for _, raw := range seedNodes {
		u := normaliseURL(raw)
		if u != "" && !visited[u] {
			visited[u] = true
			normal = append(normal, u)
		}
	}

	for hasQueued(exact, allowAll, normal) && len(visited) <= maxNodes {
		nodeURL := nextNode(&exact, &allowAll, &normal)

		block, _ := fetchBlock(client, nodeURL, fp)
		if block != nil {
			copies = append(copies, NodeBlock{nodeURL, block})

			if tc != nil {
				if all, err := fetchAllBlocks(client, nodeURL); err == nil && all != nil {
					for _, b := range all {
						if b.Fingerprint == "" {
							continue
						}
						existing, ok := accumulated[b.Fingerprint]
						if !ok || len(b.SigEntries) > len(existing.SigEntries) {
							accumulated[b.Fingerprint] = b
						}
					}
				}

				g := trust.Build(blockSlice(accumulated))
				sc := trust.Score(g, fp, strings.ToUpper(tc.RootFP), tc.MaxDepth)
				if sc >= tc.Threshold {
					best := bestCopy(copies)
					return BlockResult{
						Found:      true,
						NodeURL:    best.NodeURL,
						Block:      best.Block,
						NodesTried: len(visited),
						TrustScore: sc,
						AllCopies:  copies,
					}
				}
			}
		}

		if wk, err := fetchWellKnown(client, nodeURL); err == nil {
			enqueuePeers(wk, domainHint, &exact, &allowAll, &normal, visited)
		}
	}

	if len(copies) == 0 {
		score := -1
		if tc != nil {
			score = 0
		}
		return BlockResult{
			Found:      false,
			NodesTried: len(visited),
			TrustScore: score,
		}
	}

	best := bestCopy(copies)
	score := -1
	if tc != nil {
		g := trust.Build(blockSlice(accumulated))
		score = trust.Score(g, fp, strings.ToUpper(tc.RootFP), tc.MaxDepth)
	}
	return BlockResult{
		Found:      true,
		NodeURL:    best.NodeURL,
		Block:      best.Block,
		NodesTried: len(visited),
		TrustScore: score,
		AllCopies:  copies,
	}
}

// FindBlocksByEmail searches for blocks matching an email address across the peer graph.
//
// Visits every reachable node (BFS, up to maxNodes) and collects all matching blocks.
// Deduplicates by fingerprint; for each fingerprint the copy with the longest sig chain
// is kept.
func FindBlocksByEmail(
	email string,
	seedNodes []string,
	maxNodes int,
	timeout time.Duration,
) EmailResult {
	domain := domainFromEmail(email)
	client := &http.Client{Timeout: timeout}

	visited := map[string]bool{}
	var exact, allowAll, normal []string
	best := map[string]NodeBlock{} // fp -> best NodeBlock

	for _, raw := range seedNodes {
		u := normaliseURL(raw)
		if u != "" && !visited[u] {
			visited[u] = true
			normal = append(normal, u)
		}
	}

	for hasQueued(exact, allowAll, normal) && len(visited) <= maxNodes {
		nodeURL := nextNode(&exact, &allowAll, &normal)

		func() {
			resp, err := client.Get(strings.TrimRight(nodeURL, "/") + "/search?q=" + url.QueryEscape(email))
			if err != nil {
				return
			}
			defer resp.Body.Close()
			if resp.StatusCode != 200 {
				return
			}
			var blocks []*chain.Block
			if json.NewDecoder(resp.Body).Decode(&blocks) != nil {
				return
			}
			for _, b := range blocks {
				if b.Fingerprint == "" {
					continue
				}
				fp := strings.ToUpper(b.Fingerprint)
				existing, ok := best[fp]
				if !ok || len(b.SigEntries) > len(existing.Block.SigEntries) {
					best[fp] = NodeBlock{nodeURL, b}
				}
			}
		}()

		if wk, err := fetchWellKnown(client, nodeURL); err == nil {
			enqueuePeers(wk, domain, &exact, &allowAll, &normal, visited)
		}
	}

	blocks := make([]NodeBlock, 0, len(best))
	for _, nb := range best {
		blocks = append(blocks, nb)
	}
	return EmailResult{Blocks: blocks, NodesTried: len(visited)}
}
