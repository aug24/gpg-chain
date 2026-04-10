// GPG Chain node binary.
package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/aug24/gpg-chain/internal/api"
	"github.com/aug24/gpg-chain/internal/p2p"
	"github.com/aug24/gpg-chain/internal/store"
)

func main() {
	addr := flag.String("addr", "0.0.0.0:8080", "listen address (host:port)")
	storeFile := flag.String("store", "./data/chain.db", "path to SQLite store file")
	peersFlag := flag.String("peers", "", "comma-separated bootstrap peer URLs")
	domainsFlag := flag.String("domains", "", "comma-separated permitted email domains")
	allowAll := flag.Bool("allow-all-domains", false, "accept keys from any domain")
	nodeURL := flag.String("node-url", "", "public URL of this node ($GPGCHAIN_NODE_URL)")
	allowPrivatePeers := flag.Bool("allow-private-peers", false, "skip private IP rejection (containers only)")
	maxPeers := flag.Int("max-peers", 50, "maximum number of peers")
	flag.Parse()

	// Environment variable overrides
	if v := os.Getenv("GPGCHAIN_STORE_DIR"); v != "" && *storeFile == "./data/chain.db" {
		*storeFile = v + "/chain.db"
	}
	if v := os.Getenv("GPGCHAIN_NODE_URL"); v != "" && *nodeURL == "" {
		*nodeURL = v
	}
	if v := os.Getenv("GPGCHAIN_ALLOW_ALL"); (v == "true" || v == "1") && !*allowAll {
		*allowAll = true
	}
	if v := os.Getenv("GPGCHAIN_DOMAINS"); v != "" && *domainsFlag == "" {
		*domainsFlag = v
	}
	if v := os.Getenv("GPGCHAIN_ALLOW_PRIVATE_PEERS"); (v == "true" || v == "1") && !*allowPrivatePeers {
		*allowPrivatePeers = true
	}

	var domains []string
	if *domainsFlag != "" {
		for _, d := range strings.Split(*domainsFlag, ",") {
			d = strings.TrimSpace(d)
			if d != "" {
				domains = append(domains, d)
			}
		}
	}

	// Ensure store directory exists
	if idx := strings.LastIndex(*storeFile, "/"); idx > 0 {
		dir := (*storeFile)[:idx]
		if err := os.MkdirAll(dir, 0755); err != nil {
			log.Fatalf("failed to create store directory %s: %v", dir, err)
		}
	}

	st, err := store.Open(*storeFile)
	if err != nil {
		log.Fatalf("failed to open store: %v", err)
	}

	peers := p2p.NewPeerList(*maxPeers)
	gossip := p2p.NewGossip(peers, 3)

	syncCfg := p2p.SyncConfig{
		Store:    st,
		Domains:  domains,
		AllowAll: *allowAll,
	}

	cfg := &api.Config{
		Store:             st,
		Gossip:            gossip,
		Peers:             peers,
		Domains:           domains,
		AllowAll:          *allowAll,
		NodeURL:           *nodeURL,
		AllowPrivatePeers: *allowPrivatePeers,
		MaxPeers:          *maxPeers,
		SyncCfg:           syncCfg,
	}

	handler := api.NewRouter(cfg)

	// Bootstrap peers
	if *peersFlag != "" {
		for _, peerURL := range strings.Split(*peersFlag, ",") {
			peerURL = strings.TrimSpace(peerURL)
			if peerURL != "" {
				peers.Add(peerURL) //nolint:errcheck
				go p2p.SyncWithPeer(peerURL, syncCfg)
			}
		}
	}

	log.Printf("gpgchain node listening on %s (allow_all=%v domains=%v)", *addr, *allowAll, domains)
	if err := http.ListenAndServe(*addr, handler); err != nil {
		log.Fatal(err)
	}
}
