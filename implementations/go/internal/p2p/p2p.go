// Package p2p handles peer management, gossip, and sync.
package p2p

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/aug24/gpg-chain/internal/chain"
	"github.com/aug24/gpg-chain/internal/gpg"
	"github.com/aug24/gpg-chain/internal/store"
)

const seenTTL = time.Hour

// PeerMeta holds the cached metadata fetched from a peer's well-known endpoint.
type PeerMeta struct {
	Domains  []string
	AllowAll bool
}

// PeerList manages the set of known peer URLs.
type PeerList struct {
	mu      sync.RWMutex
	peers   []string
	maxSize int
	metaMu  sync.RWMutex
	meta    map[string]PeerMeta // peer URL → cached well-known metadata
}

func NewPeerList(maxSize int) *PeerList {
	return &PeerList{maxSize: maxSize, meta: make(map[string]PeerMeta)}
}

// Add appends url if not already present and under capacity.
func (p *PeerList) Add(url string) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, existing := range p.peers {
		if existing == url {
			return nil // already present
		}
	}
	if len(p.peers) >= p.maxSize {
		return fmt.Errorf("peer list at capacity (%d)", p.maxSize)
	}
	p.peers = append(p.peers, url)
	return nil
}

func (p *PeerList) All() []string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return append([]string{}, p.peers...)
}

func (p *PeerList) Contains(url string) bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	for _, u := range p.peers {
		if u == url {
			return true
		}
	}
	return false
}

func (p *PeerList) Len() int {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return len(p.peers)
}

// SetMeta records the cached well-known metadata for a peer URL.
func (p *PeerList) SetMeta(url string, m PeerMeta) {
	p.metaMu.Lock()
	defer p.metaMu.Unlock()
	p.meta[url] = m
}

// PeerNode holds a peer URL together with its declared domains and allow_all flag.
type PeerNode struct {
	URL      string   `json:"url"`
	Domains  []string `json:"domains"`
	AllowAll bool     `json:"allow_all"`
}

// PeerNodes returns all known peers with their cached metadata.
// If metadata has not yet been fetched the fields default to empty/false.
func (p *PeerList) PeerNodes() []PeerNode {
	p.mu.RLock()
	peers := append([]string{}, p.peers...)
	p.mu.RUnlock()

	p.metaMu.RLock()
	defer p.metaMu.RUnlock()

	nodes := make([]PeerNode, 0, len(peers))
	for _, u := range peers {
		m := p.meta[u]
		if m.Domains == nil {
			m.Domains = []string{}
		}
		nodes = append(nodes, PeerNode{URL: u, Domains: m.Domains, AllowAll: m.AllowAll})
	}
	return nodes
}

// seenEntry tracks when an event was added to the seen set.
type seenEntry struct {
	at time.Time
}

// Gossip fans out events to K randomly selected peers.
type Gossip struct {
	peers  *PeerList
	fanout int

	mu   sync.Mutex
	seen map[string]seenEntry
}

func NewGossip(peers *PeerList, fanout int) *Gossip {
	return &Gossip{
		peers:  peers,
		fanout: fanout,
		seen:   make(map[string]seenEntry),
	}
}

func (g *Gossip) isSeen(id string) bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	e, ok := g.seen[id]
	if !ok {
		return false
	}
	if time.Since(e.at) > seenTTL {
		delete(g.seen, id)
		return false
	}
	return true
}

func (g *Gossip) markSeen(id string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.seen[id] = seenEntry{at: time.Now()}
}

func (g *Gossip) pickTargets(origin string) []string {
	all := g.peers.All()
	var candidates []string
	for _, p := range all {
		if p != origin {
			candidates = append(candidates, p)
		}
	}
	rand.Shuffle(len(candidates), func(i, j int) { candidates[i], candidates[j] = candidates[j], candidates[i] })
	k := g.fanout
	if k > len(candidates) {
		k = len(candidates)
	}
	return candidates[:k]
}

func postJSON(url string, body any) {
	data, err := json.Marshal(body)
	if err != nil {
		return
	}
	resp, err := http.Post(url, "application/json", bytes.NewReader(data)) //nolint:gosec
	if err != nil {
		return
	}
	resp.Body.Close()
}

// GossipBlock forwards block to K random peers, skipping origin.
func (g *Gossip) GossipBlock(block *chain.Block, origin string) {
	if g.isSeen(block.Hash) {
		return
	}
	g.markSeen(block.Hash)
	body := map[string]any{"block": blockToMap(block)}
	for _, peer := range g.pickTargets(origin) {
		go postJSON(peer+"/p2p/block", body)
	}
}

// GossipSig forwards a SigEntry to K random peers.
func (g *Gossip) GossipSig(fp string, entry *chain.SigEntry, origin string) {
	if g.isSeen(entry.Hash) {
		return
	}
	g.markSeen(entry.Hash)
	body := map[string]any{"fingerprint": fp, "entry": sigEntryToMap(entry)}
	for _, peer := range g.pickTargets(origin) {
		go postJSON(peer+"/p2p/sign", body)
	}
}

// GossipRevoke forwards a revocation to K random peers.
func (g *Gossip) GossipRevoke(fp string, revocationSig string, origin string) {
	eventID := fp + ".revoke"
	if g.isSeen(eventID) {
		return
	}
	g.markSeen(eventID)
	body := map[string]any{"fingerprint": fp, "revocation_sig": revocationSig}
	for _, peer := range g.pickTargets(origin) {
		go postJSON(peer+"/p2p/revoke", body)
	}
}

// SyncConfig holds parameters needed for sync validation.
type SyncConfig struct {
	Store     store.Store
	Domains   []string
	AllowAll  bool
}

// SyncWithPeer performs connect-time sync: exchange hashes, fetch/push missing data.
func SyncWithPeer(peerURL string, cfg SyncConfig) {
	base := strings.TrimRight(peerURL, "/")

	// Fetch peer's hash map
	resp, err := http.Get(base + "/p2p/hashes") //nolint:gosec
	if err != nil {
		log.Printf("sync: failed to fetch hashes from %s: %v", peerURL, err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return
	}
	var peerHashes map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&peerHashes); err != nil {
		return
	}

	localHashes, err := cfg.Store.Hashes()
	if err != nil {
		return
	}

	// Fetch blocks peer has that we don't; sync sig chains that differ
	for fp, peerHead := range peerHashes {
		localHead, ok := localHashes[fp]
		if !ok {
			fetchAndStoreBlock(base, fp, cfg)
		} else if localHead != peerHead {
			syncSigChain(base, fp, cfg)
		}
	}

	// Push blocks we have that peer is missing
	for fp := range localHashes {
		if _, ok := peerHashes[fp]; !ok {
			block, _ := cfg.Store.Get(fp)
			if block != nil {
				go postJSON(base+"/p2p/block", map[string]any{"block": blockToMap(block)})
			}
		}
	}
}

// CrossValidate compares hash maps with all peers; returns fingerprints with discrepancies.
func CrossValidate(peers *PeerList, st store.Store) []string {
	localHashes, err := st.Hashes()
	if err != nil {
		return nil
	}
	var mismatches []string
	for _, peerURL := range peers.All() {
		base := strings.TrimRight(peerURL, "/")
		resp, err := http.Get(base + "/p2p/hashes") //nolint:gosec
		if err != nil {
			continue
		}
		var peerHashes map[string]string
		json.NewDecoder(resp.Body).Decode(&peerHashes) //nolint:errcheck
		resp.Body.Close()

		for fp, localHead := range localHashes {
			peerHead, ok := peerHashes[fp]
			if ok && peerHead != localHead {
				log.Printf("cross_validate: mismatch fp=%s local=%s peer(%s)=%s",
					fp, localHead, peerURL, peerHead)
				mismatches = append(mismatches, fp)
			} else if !ok {
				log.Printf("cross_validate: peer %s missing block %s", peerURL, fp)
			}
		}
	}
	return mismatches
}

func fetchAndStoreBlock(base, fingerprint string, cfg SyncConfig) {
	resp, err := http.Get(base + "/block/" + fingerprint) //nolint:gosec
	if err != nil || resp.StatusCode != http.StatusOK {
		return
	}
	defer resp.Body.Close()
	var data map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return
	}
	validateAndStore(data, base, cfg)
}

// FetchBlockFromPeers tries each known peer to fetch and store a block by fingerprint.
// Returns true if the block was successfully fetched from any peer.
func FetchBlockFromPeers(peers *PeerList, fingerprint string, cfg SyncConfig) bool {
	for _, peerURL := range peers.All() {
		base := strings.TrimRight(peerURL, "/")
		fetchAndStoreBlock(base, fingerprint, cfg)
		if b, _ := cfg.Store.Get(fingerprint); b != nil {
			return true
		}
	}
	return false
}

func validateAndStore(data map[string]any, fetchBase string, cfg SyncConfig) {
	armoredKey, _ := data["armored_key"].(string)
	selfSig, _ := data["self_sig"].(string)
	submitTS, _ := toInt64(data["submit_timestamp"])

	fp, uids, err := gpg.ParseArmoredKey(armoredKey)
	if err != nil {
		return
	}
	if err := gpg.CheckKeyStrength(armoredKey); err != nil {
		return
	}
	if !cfg.AllowAll {
		domains := gpg.ExtractEmailDomains(uids)
		if !domainAllowed(domains, cfg.Domains) {
			return
		}
	}

	payload := gpg.SubmitPayload(fp, armoredKey, submitTS)
	if !gpg.VerifyDetachedSig(payload, selfSig, armoredKey) {
		return
	}

	existing, _ := cfg.Store.Get(fp)
	if existing != nil {
		return
	}

	block := &chain.Block{
		Hash:            chain.ComputeBlockHash(fp, armoredKey, selfSig),
		Fingerprint:     fp,
		ArmoredKey:      armoredKey,
		UIDs:            uids,
		SubmitTimestamp: submitTS,
		SelfSig:         selfSig,
	}
	if err := cfg.Store.Add(block); err != nil {
		return
	}

	if sigChainRaw, ok := data["sig_chain"].([]any); ok {
		applySigEntries(fp, sigChainRaw, fetchBase, cfg)
	}
}

func syncSigChain(base, fingerprint string, cfg SyncConfig) {
	resp, err := http.Get(base + "/block/" + fingerprint) //nolint:gosec
	if err != nil || resp.StatusCode != http.StatusOK {
		return
	}
	defer resp.Body.Close()
	var data map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return
	}
	if sigChainRaw, ok := data["sig_chain"].([]any); ok {
		applySigEntries(fingerprint, sigChainRaw, base, cfg)
	}
}

// applySigEntries verifies and stores sig chain entries from a peer.
// fetchBase is the peer's base URL — used to fetch any signer blocks that are
// not yet in the local store (can happen when sigs and blocks arrive out of order).
func applySigEntries(fingerprint string, sigChainRaw []any, fetchBase string, cfg SyncConfig) {
	st := cfg.Store
	block, _ := st.Get(fingerprint)
	if block == nil {
		return
	}
	existing := make(map[string]bool)
	for _, e := range block.SigEntries {
		existing[e.SignerFingerprint] = true
	}

	for _, raw := range sigChainRaw {
		eMap, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		signerFP, _ := eMap["signer_fingerprint"].(string)
		if existing[signerFP] {
			continue
		}
		sig, _ := eMap["sig"].(string)
		ts, _ := toInt64(eMap["timestamp"])
		prevHash, _ := eMap["prev_hash"].(string)
		claimedHash, _ := eMap["hash"].(string)
		signerArmoredKey, _ := eMap["signer_armored_key"].(string)
		sourceNode, _ := eMap["source_node"].(string)

		var signerKey string
		if signerArmoredKey != "" {
			signerKey = signerArmoredKey
		} else {
			signerBlock, _ := st.Get(signerFP)
			if signerBlock == nil && fetchBase != "" {
				// Signer block hasn't arrived yet — fetch it from the peer we're syncing with.
				fetchAndStoreBlock(fetchBase, signerFP, cfg)
				signerBlock, _ = st.Get(signerFP)
			}
			if signerBlock == nil {
				continue
			}
			signerKey = signerBlock.ArmoredKey
		}

		payload := gpg.TrustPayload(block.Hash, signerFP, ts)
		if !gpg.VerifyDetachedSig(payload, sig, signerKey) {
			log.Printf("DEBUG applySigEntries: sig verify FAILED fp=%s signerFP=%s", fingerprint, signerFP)
			continue
		}
		log.Printf("DEBUG applySigEntries: sig verify ok fp=%s signerFP=%s", fingerprint, signerFP)

		computedHash := chain.ComputeSigEntryHash(prevHash, signerFP, sig, ts)
		if claimedHash != "" && claimedHash != computedHash {
			continue
		}

		entry := &chain.SigEntry{
			Hash:              computedHash,
			PrevHash:          prevHash,
			SignerFingerprint: signerFP,
			Sig:               sig,
			Timestamp:         ts,
			SignerArmoredKey:  signerArmoredKey,
			SourceNode:        sourceNode,
		}
		if err := st.AddSig(fingerprint, entry); err == nil {
			existing[signerFP] = true
			// Refresh block for next iteration
			block, _ = st.Get(fingerprint)
			if block == nil {
				break
			}
		}
	}
}

func domainAllowed(keyDomains, allowList []string) bool {
	for _, kd := range keyDomains {
		for _, a := range allowList {
			if kd == a {
				return true
			}
		}
	}
	return false
}

func toInt64(v any) (int64, bool) {
	switch x := v.(type) {
	case int64:
		return x, true
	case float64:
		return int64(x), true
	case int:
		return int64(x), true
	}
	return 0, false
}

func blockToMap(b *chain.Block) map[string]any {
	sigChain := make([]any, 0, len(b.SigEntries))
	for _, e := range b.SigEntries {
		sigChain = append(sigChain, sigEntryToMap(e))
	}
	return map[string]any{
		"hash":             b.Hash,
		"fingerprint":      b.Fingerprint,
		"armored_key":      b.ArmoredKey,
		"uids":             b.UIDs,
		"submit_timestamp": b.SubmitTimestamp,
		"self_sig":         b.SelfSig,
		"sig_chain_head":   b.SigChainHead,
		"sig_chain":        sigChain,
		"revoked":          b.Revoked,
		"revocation_sig":   b.RevocationSig,
	}
}

func sigEntryToMap(e *chain.SigEntry) map[string]any {
	m := map[string]any{
		"hash":               e.Hash,
		"prev_hash":          e.PrevHash,
		"signer_fingerprint": e.SignerFingerprint,
		"sig":                e.Sig,
		"timestamp":          e.Timestamp,
	}
	if e.SignerArmoredKey != "" {
		m["signer_armored_key"] = e.SignerArmoredKey
	}
	if e.SourceNode != "" {
		m["source_node"] = e.SourceNode
	}
	return m
}
