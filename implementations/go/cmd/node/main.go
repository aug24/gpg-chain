// GPG Chain node binary.
package main

import (
	"flag"
	"log"
	"net/http"

	"github.com/aug24/gpg-chain/internal/api"
)

func main() {
	addr := flag.String("addr", "0.0.0.0:8080", "listen address (host:port)")
	storeFile := flag.String("store", "./data/chain.db", "path to SQLite store file")
	peers := flag.String("peers", "", "comma-separated bootstrap peer URLs")
	domains := flag.String("domains", "", "comma-separated permitted email domains")
	allowAll := flag.Bool("allow-all-domains", false, "accept keys from any domain")
	nodeURL := flag.String("node-url", "", "public URL of this node")
	flag.Parse()

	_ = storeFile
	_ = peers
	_ = domains
	_ = allowAll
	_ = nodeURL

	handler := api.NewRouter()
	log.Printf("gpgchain node listening on %s", *addr)
	if err := http.ListenAndServe(*addr, handler); err != nil {
		log.Fatal(err)
	}
}
