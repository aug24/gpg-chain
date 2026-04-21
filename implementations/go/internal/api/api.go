// Package api defines the HTTP router and all route handlers.
package api

import (
	"bytes"
	"encoding/json"
	"log"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/aug24/gpg-chain/internal/chain"
	"github.com/aug24/gpg-chain/internal/gpg"
	"github.com/aug24/gpg-chain/internal/p2p"
	"github.com/aug24/gpg-chain/internal/store"
)

// Config holds the node's runtime configuration passed to all handlers.
type Config struct {
	Store             store.Store
	Gossip            *p2p.Gossip
	Peers             *p2p.PeerList
	Domains           []string
	AllowAll          bool
	NodeURL           string
	AllowPrivatePeers bool
	MaxPeers          int
	SyncCfg           p2p.SyncConfig
}

// NewRouter builds and returns the chi router with all routes registered.
func NewRouter(cfg *Config) http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/blocks", cfg.handleListBlocks)
	r.Get("/block/{fingerprint}", cfg.handleGetBlock)
	r.Post("/block", cfg.handleAddBlock)
	r.Post("/block/{fingerprint}/sign", cfg.handleSignBlock)
	r.Post("/block/{fingerprint}/revoke", cfg.handleRevokeBlock)
	r.Get("/search", cfg.handleSearch)
	r.Get("/.well-known/gpgchain.json", cfg.handleWellKnown)

	r.Get("/peers", cfg.handleListPeers)
	r.Post("/peers", cfg.handleAddPeer)

	r.Get("/p2p/hashes", cfg.handleP2PHashes)
	r.Get("/p2p/block/{hash}", cfg.handleP2PGetBlock)
	r.Post("/p2p/block", cfg.handleP2PReceiveBlock)
	r.Post("/p2p/sign", cfg.handleP2PReceiveSig)
	r.Post("/p2p/revoke", cfg.handleP2PReceiveRevoke)
	r.Post("/p2p/sync", cfg.handleP2PSync)

	return r
}

// --- serialisation helpers ---

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v) //nolint:errcheck
}

func errJSON(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func decodeBody(r *http.Request) (map[string]any, error) {
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		return nil, err
	}
	return body, nil
}

func getString(m map[string]any, key string) string {
	v, _ := m[key].(string)
	return v
}

func getInt64(m map[string]any, key string) (int64, bool) {
	switch x := m[key].(type) {
	case float64:
		return int64(x), true
	case int64:
		return x, true
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
	revSig := b.RevocationSig
	if revSig == "" {
		revSig = ""
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
		"revocation_sig":   revSig,
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

// --- public endpoints ---

func (cfg *Config) handleListBlocks(w http.ResponseWriter, r *http.Request) {
	blocks, err := cfg.Store.All()
	if err != nil {
		errJSON(w, http.StatusInternalServerError, "failed to list blocks")
		return
	}
	result := make([]any, 0, len(blocks))
	for _, b := range blocks {
		result = append(result, blockToMap(b))
	}
	writeJSON(w, http.StatusOK, result)
}

func (cfg *Config) handleGetBlock(w http.ResponseWriter, r *http.Request) {
	fp := chi.URLParam(r, "fingerprint")
	block, err := cfg.Store.Get(fp)
	if err != nil {
		errJSON(w, http.StatusInternalServerError, "store error")
		return
	}
	if block == nil {
		errJSON(w, http.StatusNotFound, "block not found")
		return
	}
	writeJSON(w, http.StatusOK, blockToMap(block))
}

func (cfg *Config) handleAddBlock(w http.ResponseWriter, r *http.Request) {
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	armoredKey := getString(body, "armored_key")
	selfSig := getString(body, "self_sig")
	if armoredKey == "" || selfSig == "" {
		errJSON(w, http.StatusBadRequest, "armored_key and self_sig are required")
		return
	}

	fp, uids, err := gpg.ParseArmoredKey(armoredKey)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid armored key: "+err.Error())
		return
	}
	if err := gpg.CheckKeyStrength(armoredKey); err != nil {
		errJSON(w, http.StatusBadRequest, "key too weak: "+err.Error())
		return
	}

	keyDomains := gpg.ExtractEmailDomains(uids)
	if len(keyDomains) == 0 {
		errJSON(w, http.StatusBadRequest, "key has no email UID")
		return
	}
	if !cfg.AllowAll && !domainAllowed(keyDomains, cfg.Domains) {
		errJSON(w, http.StatusForbidden, "key domain not in allowlist")
		return
	}

	ts, ok := getInt64(body, "submit_timestamp")
	if !ok {
		ts = time.Now().Unix()
	}

	payload := gpg.SubmitPayload(fp, armoredKey, ts)
	if !gpg.VerifyDetachedSig(payload, selfSig, armoredKey) {
		errJSON(w, http.StatusBadRequest, "self_sig verification failed")
		return
	}

	existing, _ := cfg.Store.Get(fp)
	if existing != nil {
		errJSON(w, http.StatusConflict, "block already exists for this fingerprint")
		return
	}

	block := &chain.Block{
		Hash:            chain.ComputeBlockHash(fp, armoredKey, selfSig),
		Fingerprint:     fp,
		ArmoredKey:      armoredKey,
		UIDs:            uids,
		SubmitTimestamp: ts,
		SelfSig:         selfSig,
	}
	if err := cfg.Store.Add(block); err != nil {
		errJSON(w, http.StatusConflict, "block already exists for this fingerprint")
		return
	}

	go cfg.Gossip.GossipBlock(block, "")
	writeJSON(w, http.StatusCreated, blockToMap(block))
}

func (cfg *Config) handleSignBlock(w http.ResponseWriter, r *http.Request) {
	fp := chi.URLParam(r, "fingerprint")
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	signerFP := getString(body, "signer_fingerprint")
	sig := getString(body, "sig")
	if signerFP == "" || sig == "" {
		errJSON(w, http.StatusBadRequest, "signer_fingerprint and sig are required")
		return
	}
	ts, ok := getInt64(body, "timestamp")
	if !ok {
		ts = time.Now().Unix()
	}
	signerArmoredKey := getString(body, "signer_armored_key")
	sourceNode := getString(body, "source_node")

	block, _ := cfg.Store.Get(fp)
	if block == nil {
		errJSON(w, http.StatusNotFound, "block not found")
		return
	}
	if block.Revoked {
		errJSON(w, http.StatusConflict, "block is revoked")
		return
	}

	var signerKey string
	if signerArmoredKey != "" {
		if err := gpg.CheckKeyStrength(signerArmoredKey); err != nil {
			errJSON(w, http.StatusBadRequest, "signer key too weak: "+err.Error())
			return
		}
		signerKey = signerArmoredKey
	} else {
		signerBlock, _ := cfg.Store.Get(signerFP)
		if signerBlock == nil {
			errJSON(w, http.StatusBadRequest, "signer block not found on ledger")
			return
		}
		signerKey = signerBlock.ArmoredKey
	}

	payload := gpg.TrustPayload(block.Hash, signerFP, ts)
	if !gpg.VerifyDetachedSig(payload, sig, signerKey) {
		errJSON(w, http.StatusBadRequest, "sig verification failed")
		return
	}

	for _, existing := range block.SigEntries {
		if existing.SignerFingerprint == signerFP {
			errJSON(w, http.StatusConflict, "signer has already signed this block")
			return
		}
	}

	prevHash := block.SigChainHead
	if prevHash == "" {
		prevHash = block.Hash
	}
	entryHash := chain.ComputeSigEntryHash(prevHash, signerFP, sig, ts)
	entry := &chain.SigEntry{
		Hash:              entryHash,
		PrevHash:          prevHash,
		SignerFingerprint: signerFP,
		Sig:               sig,
		Timestamp:         ts,
		SignerArmoredKey:  signerArmoredKey,
		SourceNode:        sourceNode,
	}
	cfg.Store.AddSig(fp, entry) //nolint:errcheck
	go cfg.Gossip.GossipSig(fp, entry, "")

	updated, _ := cfg.Store.Get(fp)
	writeJSON(w, http.StatusOK, blockToMap(updated))
}

func (cfg *Config) handleRevokeBlock(w http.ResponseWriter, r *http.Request) {
	fp := chi.URLParam(r, "fingerprint")
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	sig := getString(body, "sig")
	if sig == "" {
		errJSON(w, http.StatusBadRequest, "sig is required")
		return
	}

	block, _ := cfg.Store.Get(fp)
	if block == nil {
		errJSON(w, http.StatusNotFound, "block not found")
		return
	}
	if block.Revoked {
		errJSON(w, http.StatusConflict, "block is already revoked")
		return
	}

	payload := gpg.RevokePayload(fp, block.Hash)
	if !gpg.VerifyDetachedSig(payload, sig, block.ArmoredKey) {
		errJSON(w, http.StatusForbidden, "revocation sig verification failed")
		return
	}

	cfg.Store.Revoke(fp, sig) //nolint:errcheck
	go cfg.Gossip.GossipRevoke(fp, sig, "")

	updated, _ := cfg.Store.Get(fp)
	writeJSON(w, http.StatusOK, blockToMap(updated))
}

func (cfg *Config) handleSearch(w http.ResponseWriter, r *http.Request) {
	q := strings.ToLower(r.URL.Query().Get("q"))
	blocks, err := cfg.Store.All()
	if err != nil {
		errJSON(w, http.StatusInternalServerError, "store error")
		return
	}
	results := make([]any, 0)
	for _, b := range blocks {
		for _, uid := range b.UIDs {
			if strings.Contains(strings.ToLower(uid), q) {
				results = append(results, blockToMap(b))
				break
			}
		}
	}
	writeJSON(w, http.StatusOK, results)
}

func (cfg *Config) handleWellKnown(w http.ResponseWriter, r *http.Request) {
	peers := cfg.Peers.All()
	if peers == nil {
		peers = []string{}
	}
	domains := cfg.Domains
	if domains == nil {
		domains = []string{}
	}
	peerNodes := cfg.Peers.PeerNodes()
	if peerNodes == nil {
		peerNodes = []p2p.PeerNode{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"node_url":   cfg.NodeURL,
		"domains":    domains,
		"allow_all":  cfg.AllowAll,
		"peers":      peers,
		"peer_nodes": peerNodes,
	})
}

// --- peer management ---

func (cfg *Config) handleListPeers(w http.ResponseWriter, r *http.Request) {
	peers := cfg.Peers.All()
	if peers == nil {
		peers = []string{}
	}
	writeJSON(w, http.StatusOK, peers)
}

func (cfg *Config) handleAddPeer(w http.ResponseWriter, r *http.Request) {
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	addr := getString(body, "addr")
	if addr == "" {
		errJSON(w, http.StatusBadRequest, "addr is required")
		return
	}

	parsed, err := url.Parse(addr)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		errJSON(w, http.StatusBadRequest, "URL scheme must be http or https")
		return
	}

	if cfg.Peers.Len() >= cfg.MaxPeers && !cfg.Peers.Contains(addr) {
		errJSON(w, http.StatusTooManyRequests, "peer list is at capacity")
		return
	}

	{
		host := parsed.Hostname()
		addrs, err := net.LookupHost(host)
		if err != nil {
			errJSON(w, http.StatusBadRequest, "could not resolve peer address")
			return
		}
		for _, a := range addrs {
			ip := net.ParseIP(a)
			if ip == nil {
				continue
			}
			// Always reject loopback — a node must never peer with itself.
			if ip.IsLoopback() {
				errJSON(w, http.StatusBadRequest, "loopback addresses are not allowed")
				return
			}
			if !cfg.AllowPrivatePeers && (ip.IsPrivate() || ip.IsLinkLocalUnicast()) {
				errJSON(w, http.StatusBadRequest, "private or loopback addresses are not allowed")
				return
			}
		}
	}

	checkURL := strings.TrimRight(addr, "/") + "/peers"
	resp, err := http.Get(checkURL) //nolint:gosec
	if err != nil {
		errJSON(w, http.StatusBadRequest, "peer is not reachable")
		return
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		errJSON(w, http.StatusBadRequest, "peer reachability check failed")
		return
	}

	cfg.Peers.Add(addr) //nolint:errcheck

	// Fetch peer's well-known metadata in background for discovery prioritisation.
	go func(peerURL string) {
		wkURL := strings.TrimRight(peerURL, "/") + "/.well-known/gpgchain.json"
		resp, err := http.Get(wkURL) //nolint:gosec
		if err != nil {
			return
		}
		defer resp.Body.Close()
		var wk struct {
			Domains  []string `json:"domains"`
			AllowAll bool     `json:"allow_all"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&wk); err != nil {
			return
		}
		cfg.Peers.SetMeta(peerURL, p2p.PeerMeta{Domains: wk.Domains, AllowAll: wk.AllowAll})
	}(addr)

	if cfg.NodeURL != "" {
		go registerSelfWithPeer(addr, cfg.NodeURL)
	}
	syncCfg := cfg.SyncCfg
	go p2p.SyncWithPeer(addr, syncCfg)

	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func registerSelfWithPeer(peerURL, myNodeURL string) {
	body, _ := json.Marshal(map[string]string{"addr": myNodeURL})
	resp, err := http.Post( //nolint:gosec
		strings.TrimRight(peerURL, "/")+"/peers",
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		return
	}
	resp.Body.Close()
}

// --- p2p inter-node endpoints ---

// handleP2PSync triggers an immediate sync with all known peers.
// Useful for testing and operational purposes when gossip delivery may have been incomplete.
func (cfg *Config) handleP2PSync(w http.ResponseWriter, r *http.Request) {
	peers := cfg.Peers.All()
	log.Printf("DEBUG p2p/sync: triggering sync with %d peers: %v", len(peers), peers)
	syncCfg := cfg.SyncCfg
	for _, peer := range peers {
		go p2p.SyncWithPeer(peer, syncCfg)
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (cfg *Config) handleP2PHashes(w http.ResponseWriter, r *http.Request) {
	hashes, err := cfg.Store.Hashes()
	if err != nil {
		errJSON(w, http.StatusInternalServerError, "store error")
		return
	}
	if hashes == nil {
		hashes = map[string]string{}
	}
	writeJSON(w, http.StatusOK, hashes)
}

func (cfg *Config) handleP2PGetBlock(w http.ResponseWriter, r *http.Request) {
	blockHash := chi.URLParam(r, "hash")
	blocks, err := cfg.Store.All()
	if err != nil {
		errJSON(w, http.StatusInternalServerError, "store error")
		return
	}
	for _, b := range blocks {
		if b.Hash == blockHash {
			writeJSON(w, http.StatusOK, blockToMap(b))
			return
		}
	}
	errJSON(w, http.StatusNotFound, "block not found")
}

func (cfg *Config) handleP2PReceiveBlock(w http.ResponseWriter, r *http.Request) {
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	blockData, ok := body["block"].(map[string]any)
	if !ok {
		errJSON(w, http.StatusBadRequest, "block is required")
		return
	}

	armoredKey := getString(blockData, "armored_key")
	selfSig := getString(blockData, "self_sig")
	if armoredKey == "" || selfSig == "" {
		errJSON(w, http.StatusBadRequest, "block.armored_key and block.self_sig are required")
		return
	}

	fp, uids, err := gpg.ParseArmoredKey(armoredKey)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid armored key: "+err.Error())
		return
	}
	if err := gpg.CheckKeyStrength(armoredKey); err != nil {
		errJSON(w, http.StatusBadRequest, "key too weak: "+err.Error())
		return
	}
	if !cfg.AllowAll {
		keyDomains := gpg.ExtractEmailDomains(uids)
		if !domainAllowed(keyDomains, cfg.Domains) {
			errJSON(w, http.StatusBadRequest, "key domain not in allowlist")
			return
		}
	}

	blockHash := chain.ComputeBlockHash(fp, armoredKey, selfSig)
	if claimedHash := getString(blockData, "hash"); claimedHash != "" && claimedHash != blockHash {
		errJSON(w, http.StatusBadRequest, "block hash mismatch")
		return
	}

	ts, ok := getInt64(blockData, "submit_timestamp")
	if !ok {
		ts = time.Now().Unix()
	}
	payload := gpg.SubmitPayload(fp, armoredKey, ts)
	if !gpg.VerifyDetachedSig(payload, selfSig, armoredKey) {
		errJSON(w, http.StatusBadRequest, "self_sig verification failed")
		return
	}

	existing, _ := cfg.Store.Get(fp)
	if existing != nil {
		writeJSON(w, http.StatusOK, map[string]any{"ok": true})
		return
	}

	block := &chain.Block{
		Hash:            blockHash,
		Fingerprint:     fp,
		ArmoredKey:      armoredKey,
		UIDs:            uids,
		SubmitTimestamp: ts,
		SelfSig:         selfSig,
	}
	cfg.Store.Add(block) //nolint:errcheck

	origin := r.Header.Get("X-Forwarded-For")
	go cfg.Gossip.GossipBlock(block, origin)

	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (cfg *Config) handleP2PReceiveSig(w http.ResponseWriter, r *http.Request) {
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	fp := getString(body, "fingerprint")
	entryData, ok := body["entry"].(map[string]any)
	if !ok || fp == "" {
		errJSON(w, http.StatusBadRequest, "fingerprint and entry are required")
		return
	}

	signerFP := getString(entryData, "signer_fingerprint")
	sig := getString(entryData, "sig")
	prevHash := getString(entryData, "prev_hash")
	if signerFP == "" || sig == "" || prevHash == "" {
		errJSON(w, http.StatusBadRequest, "entry.signer_fingerprint, entry.sig, and entry.prev_hash are required")
		return
	}
	ts, _ := getInt64(entryData, "timestamp")
	claimedHash := getString(entryData, "hash")
	signerArmoredKey := getString(entryData, "signer_armored_key")
	sourceNode := getString(entryData, "source_node")

	block, _ := cfg.Store.Get(fp)
	if block == nil {
		errJSON(w, http.StatusBadRequest, "target block not found")
		return
	}
	if block.Revoked {
		errJSON(w, http.StatusBadRequest, "block is revoked")
		return
	}

	var signerKey string
	if signerArmoredKey != "" {
		signerKey = signerArmoredKey
	} else {
		signerBlock, _ := cfg.Store.Get(signerFP)
		if signerBlock == nil {
			// Sig may have arrived before the signer's block due to gossip ordering.
			// Try to fetch the signer block from known peers before giving up.
			p2p.FetchBlockFromPeers(cfg.Peers, signerFP, cfg.SyncCfg)
			signerBlock, _ = cfg.Store.Get(signerFP)
		}
		if signerBlock == nil {
			errJSON(w, http.StatusBadRequest, "signer block not found on ledger")
			return
		}
		signerKey = signerBlock.ArmoredKey
	}

	payload := gpg.TrustPayload(block.Hash, signerFP, ts)
	if !gpg.VerifyDetachedSig(payload, sig, signerKey) {
		log.Printf("DEBUG p2p/sign: sig verification FAILED fp=%s blockHash=%s signerFP=%s ts=%d", fp, block.Hash, signerFP, ts)
		errJSON(w, http.StatusBadRequest, "sig verification failed")
		return
	}
	for _, existing := range block.SigEntries {
		if existing.SignerFingerprint == signerFP {
			writeJSON(w, http.StatusOK, map[string]any{"ok": true})
			return
		}
	}

	computedHash := chain.ComputeSigEntryHash(prevHash, signerFP, sig, ts)
	if claimedHash != "" && claimedHash != computedHash {
		log.Printf("DEBUG p2p/sign: hash mismatch fp=%s signerFP=%s", fp, signerFP)
		errJSON(w, http.StatusBadRequest, "SigEntry hash mismatch")
		return
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
	log.Printf("DEBUG p2p/sign: storing sig fp=%s signerFP=%s", fp, signerFP)
	cfg.Store.AddSig(fp, entry) //nolint:errcheck

	origin := r.Header.Get("X-Forwarded-For")
	go cfg.Gossip.GossipSig(fp, entry, origin)

	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (cfg *Config) handleP2PReceiveRevoke(w http.ResponseWriter, r *http.Request) {
	body, err := decodeBody(r)
	if err != nil {
		errJSON(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	fp := getString(body, "fingerprint")
	revocationSig := getString(body, "revocation_sig")
	if fp == "" || revocationSig == "" {
		errJSON(w, http.StatusBadRequest, "fingerprint and revocation_sig are required")
		return
	}

	block, _ := cfg.Store.Get(fp)
	if block == nil {
		errJSON(w, http.StatusBadRequest, "block not found")
		return
	}
	if block.Revoked {
		writeJSON(w, http.StatusOK, map[string]any{"ok": true})
		return
	}

	payload := gpg.RevokePayload(fp, block.Hash)
	if !gpg.VerifyDetachedSig(payload, revocationSig, block.ArmoredKey) {
		errJSON(w, http.StatusBadRequest, "revocation sig verification failed")
		return
	}

	cfg.Store.Revoke(fp, revocationSig) //nolint:errcheck

	origin := r.Header.Get("X-Forwarded-For")
	go cfg.Gossip.GossipRevoke(fp, revocationSig, origin)

	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}
