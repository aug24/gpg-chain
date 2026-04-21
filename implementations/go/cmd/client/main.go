// GPG Chain CLI client.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/aug24/gpg-chain/internal/chain"
	"github.com/aug24/gpg-chain/internal/discovery"
	"github.com/aug24/gpg-chain/internal/gpg"
	"github.com/aug24/gpg-chain/internal/trust"
)

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func die(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}

func readFile(path, label string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		die("cannot read %s %q: %v", label, path, err)
	}
	return string(b)
}

// httpDo performs an HTTP request and returns the decoded JSON body or errors.
func httpDo(method, url string, body any) (map[string]any, int, error) {
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, 0, err
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, url, r)
	if err != nil {
		return nil, 0, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	var out map[string]any
	json.NewDecoder(resp.Body).Decode(&out) //nolint:errcheck
	return out, resp.StatusCode, nil
}

func httpGet(url string) ([]byte, int, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	return b, resp.StatusCode, err
}

// printBlock renders a block to stdout.
func printBlock(b map[string]any) {
	fp, _ := b["fingerprint"].(string)
	revoked, _ := b["revoked"].(bool)
	hash, _ := b["hash"].(string)
	ts, _ := b["submit_timestamp"].(float64)
	var uids []string
	if raw, ok := b["uids"].([]any); ok {
		for _, u := range raw {
			if s, ok := u.(string); ok {
				uids = append(uids, s)
			}
		}
	}
	status := "active"
	if revoked {
		status = "REVOKED"
	}
	var sigCount int
	if chain, ok := b["sig_chain"].([]any); ok {
		sigCount = len(chain)
	}
	fmt.Printf("Fingerprint: %s\n", fp)
	fmt.Printf("Hash:        %s\n", hash)
	fmt.Printf("UIDs:        %s\n", strings.Join(uids, ", "))
	fmt.Printf("Submitted:   %s\n", time.Unix(int64(ts), 0).UTC().Format(time.RFC3339))
	fmt.Printf("Status:      %s\n", status)
	fmt.Printf("Signatures:  %d\n", sigCount)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: gpgchain <command> [flags]")
		fmt.Fprintln(os.Stderr, "commands: add, sign, revoke, endorse, list, check, show, search, verify")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "add":
		cmdAdd()
	case "sign":
		cmdSign()
	case "revoke":
		cmdRevoke()
	case "endorse":
		cmdEndorse()
	case "list":
		cmdList()
	case "check":
		cmdCheck()
	case "show":
		cmdShow()
	case "search":
		cmdSearch()
	case "verify":
		cmdVerify()
	default:
		die("unknown command: %s", os.Args[1])
	}
}

// ---------------------------------------------------------------------------
// add
// ---------------------------------------------------------------------------

func cmdAdd() {
	fs := flag.NewFlagSet("add", flag.ExitOnError)
	keyFile := fs.String("key", "", "path to ASCII-armored public key file (required)")
	privKeyFile := fs.String("privkey", "", "path to ASCII-armored private key file (required)")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	if *keyFile == "" || *privKeyFile == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain add --key <pubkey.asc> --privkey <privkey.asc> [--server <url>]")
		os.Exit(1)
	}

	armoredKey := readFile(*keyFile, "public key")
	armoredPriv := readFile(*privKeyFile, "private key")

	fp, _, err := gpg.ParseArmoredKey(armoredKey)
	if err != nil {
		die("invalid public key: %v", err)
	}

	ts := time.Now().Unix()
	payload := gpg.SubmitPayload(fp, armoredKey, ts)
	selfSig, err := gpg.Sign(payload, armoredPriv)
	if err != nil {
		die("signing failed: %v", err)
	}

	result, status, err := httpDo("POST", strings.TrimRight(*serverURL, "/")+"/block", map[string]any{
		"armored_key":      armoredKey,
		"self_sig":         selfSig,
		"submit_timestamp": ts,
	})
	if err != nil {
		die("request failed: %v", err)
	}
	if status != 201 {
		errMsg, _ := result["error"].(string)
		die("server returned %d: %s", status, errMsg)
	}
	fmt.Printf("Added block: %s\n", fp)
}

// ---------------------------------------------------------------------------
// sign
// ---------------------------------------------------------------------------

func cmdSign() {
	fs := flag.NewFlagSet("sign", flag.ExitOnError)
	targetFP := fs.String("fingerprint", "", "fingerprint of block to sign (required)")
	signerFP := fs.String("keyid", envOr("GPGCHAIN_KEYID", ""), "signer fingerprint (required)")
	privKeyFile := fs.String("privkey", "", "path to signer's private key file (required)")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	signerKeyFile := fs.String("signer-key", "", "path to signer's public key (for off-ledger signing)")
	sourceNode := fs.String("source-node", "", "source node URL (for off-ledger signing)")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	if *targetFP == "" || *signerFP == "" || *privKeyFile == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain sign --fingerprint <fp> --keyid <fp> --privkey <privkey.asc> [--server <url>]")
		os.Exit(1)
	}

	armoredPriv := readFile(*privKeyFile, "private key")

	// Fetch target block to get its hash.
	rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/block/" + strings.ToUpper(*targetFP))
	if err != nil {
		die("fetch block failed: %v", err)
	}
	if status == 404 {
		die("block %s not found on %s", *targetFP, *serverURL)
	}
	if status != 200 {
		die("server returned %d fetching block", status)
	}
	var blockData map[string]any
	if err := json.Unmarshal(rawBody, &blockData); err != nil {
		die("invalid block response: %v", err)
	}
	blockHash, _ := blockData["hash"].(string)
	if blockHash == "" {
		die("block response missing hash field")
	}

	ts := time.Now().Unix()
	payload := gpg.TrustPayload(blockHash, strings.ToUpper(*signerFP), ts)
	sig, err := gpg.Sign(payload, armoredPriv)
	if err != nil {
		die("signing failed: %v", err)
	}

	reqBody := map[string]any{
		"signer_fingerprint": strings.ToUpper(*signerFP),
		"sig":                sig,
		"timestamp":          ts,
	}
	if *signerKeyFile != "" {
		reqBody["signer_armored_key"] = readFile(*signerKeyFile, "signer public key")
	}
	if *sourceNode != "" {
		reqBody["source_node"] = *sourceNode
	}

	result, status, err := httpDo("POST",
		strings.TrimRight(*serverURL, "/")+"/block/"+strings.ToUpper(*targetFP)+"/sign",
		reqBody,
	)
	if err != nil {
		die("request failed: %v", err)
	}
	if status != 200 {
		errMsg, _ := result["error"].(string)
		die("server returned %d: %s", status, errMsg)
	}
	fmt.Printf("Signed block %s as %s\n", strings.ToUpper(*targetFP), strings.ToUpper(*signerFP))
}

// ---------------------------------------------------------------------------
// revoke
// ---------------------------------------------------------------------------

func cmdRevoke() {
	fs := flag.NewFlagSet("revoke", flag.ExitOnError)
	fp := fs.String("fingerprint", envOr("GPGCHAIN_KEYID", ""), "fingerprint of block to revoke (defaults to --keyid / $GPGCHAIN_KEYID)")
	keyID := fs.String("keyid", envOr("GPGCHAIN_KEYID", ""), "own key fingerprint (alias for --fingerprint)")
	privKeyFile := fs.String("privkey", "", "path to own private key file (required)")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	target := *fp
	if target == "" {
		target = *keyID
	}
	if target == "" || *privKeyFile == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain revoke --fingerprint <fp> --privkey <privkey.asc> [--server <url>]")
		os.Exit(1)
	}
	target = strings.ToUpper(target)

	armoredPriv := readFile(*privKeyFile, "private key")

	rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/block/" + target)
	if err != nil {
		die("fetch block failed: %v", err)
	}
	if status == 404 {
		die("block %s not found on %s", target, *serverURL)
	}
	if status != 200 {
		die("server returned %d fetching block", status)
	}
	var blockData map[string]any
	if err := json.Unmarshal(rawBody, &blockData); err != nil {
		die("invalid block response: %v", err)
	}
	blockHash, _ := blockData["hash"].(string)
	if blockHash == "" {
		die("block response missing hash field")
	}

	payload := gpg.RevokePayload(target, blockHash)
	sig, err := gpg.Sign(payload, armoredPriv)
	if err != nil {
		die("signing failed: %v", err)
	}

	result, status, err := httpDo("POST",
		strings.TrimRight(*serverURL, "/")+"/block/"+target+"/revoke",
		map[string]any{"sig": sig},
	)
	if err != nil {
		die("request failed: %v", err)
	}
	if status != 200 {
		errMsg, _ := result["error"].(string)
		die("server returned %d: %s", status, errMsg)
	}
	fmt.Printf("Revoked block %s\n", target)
}

// ---------------------------------------------------------------------------
// endorse
// ---------------------------------------------------------------------------

// cmdEndorse signs every key that meets the trust threshold and has not yet
// been signed by the caller.  The default threshold of 2 requires at least two
// independent trust paths before the caller adds their own endorsement.
func cmdEndorse() {
	fs := flag.NewFlagSet("endorse", flag.ExitOnError)
	keyID := fs.String("keyid", envOr("GPGCHAIN_KEYID", ""), "own key fingerprint (required)")
	privKeyFile := fs.String("privkey", "", "path to own private key file (required unless --dry-run)")
	threshold := fs.Int("threshold", 2, "minimum trust score required to endorse a key")
	maxDepth := fs.Int("max-depth", 2, "maximum trust path depth")
	disjoint := fs.Bool("disjoint", false, "use vertex-disjoint path scoring (recommended with --threshold 2+)")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	dryRun := fs.Bool("dry-run", false, "print candidates without signing")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	if *keyID == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain endorse --keyid <fp> --privkey <privkey.asc> [--threshold 2] [--disjoint] [--dry-run]")
		os.Exit(1)
	}
	if !*dryRun && *privKeyFile == "" {
		fmt.Fprintln(os.Stderr, "endorse: --privkey is required unless --dry-run is set")
		os.Exit(1)
	}

	ownFP := strings.ToUpper(*keyID)

	var armoredPriv string
	if !*dryRun {
		armoredPriv = readFile(*privKeyFile, "private key")
	}

	rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/blocks")
	if err != nil {
		die("request failed: %v", err)
	}
	if status != 200 {
		die("server returned %d", status)
	}
	var blocks []*chain.Block
	if err := json.Unmarshal(rawBody, &blocks); err != nil {
		die("invalid response: %v", err)
	}

	g := trust.Build(blocks)

	var nSigned, nAlready, nBelow int

	for _, b := range blocks {
		fp := strings.ToUpper(b.Fingerprint)

		if fp == ownFP || b.Revoked {
			continue
		}

		var score int
		if *disjoint {
			score = trust.DisjointScore(g, fp, ownFP, *maxDepth)
		} else {
			score = trust.Score(g, fp, ownFP, *maxDepth)
		}
		if score < *threshold {
			nBelow++
			continue
		}

		// Already signed?
		for _, e := range b.SigEntries {
			if strings.ToUpper(e.SignerFingerprint) == ownFP {
				nAlready++
				goto nextBlock
			}
		}

		if *dryRun {
			fmt.Printf("would sign: %s  (trust=%d)  %s\n", fp, score, strings.Join(b.UIDs, ", "))
			nSigned++
			goto nextBlock
		}

		{
			ts := time.Now().Unix()
			payload := gpg.TrustPayload(b.Hash, ownFP, ts)
			sig, err := gpg.Sign(payload, armoredPriv)
			if err != nil {
				fmt.Printf("error:      %s  signing failed: %v\n", fp, err)
				goto nextBlock
			}
			result, respStatus, err := httpDo("POST",
				strings.TrimRight(*serverURL, "/")+"/block/"+fp+"/sign",
				map[string]any{
					"signer_fingerprint": ownFP,
					"sig":                sig,
					"timestamp":          ts,
				},
			)
			if err != nil {
				fmt.Printf("error:      %s  request failed: %v\n", fp, err)
				goto nextBlock
			}
			if respStatus != 200 {
				errMsg, _ := result["error"].(string)
				fmt.Printf("error:      %s  server returned %d: %s\n", fp, respStatus, errMsg)
				goto nextBlock
			}
			fmt.Printf("signed:     %s  (trust=%d)  %s\n", fp, score, strings.Join(b.UIDs, ", "))
			nSigned++
		}

	nextBlock:
	}

	fmt.Println()
	if *dryRun {
		fmt.Printf("%d key(s) would be signed  (%d already signed, %d below threshold)\n",
			nSigned, nAlready, nBelow)
	} else {
		fmt.Printf("%d key(s) signed  (%d already signed, %d below threshold)\n",
			nSigned, nAlready, nBelow)
	}
}

// ---------------------------------------------------------------------------
// list
// ---------------------------------------------------------------------------

func cmdList() {
	fs := flag.NewFlagSet("list", flag.ExitOnError)
	keyID := fs.String("keyid", envOr("GPGCHAIN_KEYID", ""), "own key fingerprint for trust evaluation")
	minTrust := fs.Int("min-trust", 0, "minimum trust score (0 = show all)")
	maxDepth := fs.Int("max-depth", 2, "maximum trust path depth")
	disjoint := fs.Bool("disjoint", false, "use vertex-disjoint path scoring")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/blocks")
	if err != nil {
		die("request failed: %v", err)
	}
	if status != 200 {
		die("server returned %d", status)
	}

	var blocks []*chain.Block
	if err := json.Unmarshal(rawBody, &blocks); err != nil {
		die("invalid response: %v", err)
	}

	rootFP := strings.ToUpper(*keyID)
	var g trust.Graph
	if rootFP != "" {
		g = trust.Build(blocks)
	}

	for _, b := range blocks {
		fp := strings.ToUpper(b.Fingerprint)
		score := -1
		if g != nil && rootFP != "" {
			if *disjoint {
				score = trust.DisjointScore(g, fp, rootFP, *maxDepth)
			} else {
				score = trust.Score(g, fp, rootFP, *maxDepth)
			}
			if score < *minTrust {
				continue
			}
		} else if *minTrust > 0 {
			continue
		}

		status := "active"
		if b.Revoked {
			status = "REVOKED"
		}
		trustStr := ""
		if score >= 0 {
			trustStr = fmt.Sprintf("  trust=%d", score)
		}
		fmt.Printf("%s  %-8s  %s%s\n", fp, status, strings.Join(b.UIDs, ", "), trustStr)
	}
}

// ---------------------------------------------------------------------------
// check
// ---------------------------------------------------------------------------

func cmdCheck() {
	fs := flag.NewFlagSet("check", flag.ExitOnError)
	targetFP := fs.String("fingerprint", "", "fingerprint to check (required)")
	keyID := fs.String("keyid", envOr("GPGCHAIN_KEYID", ""), "own key fingerprint / root of trust (required)")
	maxDepth := fs.Int("max-depth", 2, "maximum trust path depth")
	threshold := fs.Int("threshold", 1, "trust threshold")
	disjoint := fs.Bool("disjoint", false, "use vertex-disjoint path scoring")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	seeds := fs.String("seeds", "", "additional comma-separated seed node URLs")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	if *targetFP == "" || *keyID == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain check --fingerprint <fp> --keyid <fp> [--server <url>] [--threshold <n>]")
		os.Exit(1)
	}

	seedList := []string{strings.TrimRight(*serverURL, "/")}
	if *seeds != "" {
		for _, s := range strings.Split(*seeds, ",") {
			if u := strings.TrimSpace(s); u != "" {
				seedList = append(seedList, u)
			}
		}
	}

	tc := &discovery.TrustConfig{
		RootFP:    strings.ToUpper(*keyID),
		Threshold: *threshold,
		MaxDepth:  *maxDepth,
	}
	if *disjoint {
		// For disjoint scoring we do a full BFS and score afterwards.
		tc = nil
	}

	result := discovery.FindBlock(strings.ToUpper(*targetFP), seedList, "", 20, 5*time.Second, tc)

	if !result.Found {
		fmt.Printf("Block %s: NOT FOUND (tried %d nodes)\n", strings.ToUpper(*targetFP), result.NodesTried)
		os.Exit(1)
	}

	var score int
	if *disjoint {
		rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/blocks")
		if err != nil || status != 200 {
			die("failed to fetch blocks for trust evaluation")
		}
		var blocks []*chain.Block
		json.Unmarshal(rawBody, &blocks) //nolint:errcheck
		g := trust.Build(blocks)
		score = trust.DisjointScore(g, strings.ToUpper(*targetFP), strings.ToUpper(*keyID), *maxDepth)
	} else {
		score = result.TrustScore
		if score < 0 {
			score = 0
		}
	}

	trusted := score >= *threshold
	fmt.Printf("Block:      %s\n", strings.ToUpper(*targetFP))
	fmt.Printf("Found on:   %s\n", result.NodeURL)
	fmt.Printf("UIDs:       %s\n", strings.Join(result.Block.UIDs, ", "))
	fmt.Printf("Trust score: %d (threshold %d)\n", score, *threshold)
	if trusted {
		fmt.Println("Result:     TRUSTED")
	} else {
		fmt.Println("Result:     NOT TRUSTED")
		os.Exit(2)
	}
}

// ---------------------------------------------------------------------------
// show
// ---------------------------------------------------------------------------

func cmdShow() {
	fs := flag.NewFlagSet("show", flag.ExitOnError)
	fp := fs.String("fingerprint", "", "fingerprint to show (required)")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	if *fp == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain show --fingerprint <fp> [--server <url>]")
		os.Exit(1)
	}

	rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/block/" + strings.ToUpper(*fp))
	if err != nil {
		die("request failed: %v", err)
	}
	if status == 404 {
		die("block %s not found", *fp)
	}
	if status != 200 {
		die("server returned %d", status)
	}

	var blockData map[string]any
	if err := json.Unmarshal(rawBody, &blockData); err != nil {
		die("invalid response: %v", err)
	}

	printBlock(blockData)

	if sigChain, ok := blockData["sig_chain"].([]any); ok && len(sigChain) > 0 {
		fmt.Printf("\nSignature chain (%d entries):\n", len(sigChain))
		for i, raw := range sigChain {
			entry, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			signerFP, _ := entry["signer_fingerprint"].(string)
			ts, _ := entry["timestamp"].(float64)
			fmt.Printf("  [%d] signer=%s  time=%s\n", i+1, signerFP,
				time.Unix(int64(ts), 0).UTC().Format(time.RFC3339))
		}
	}
}

// ---------------------------------------------------------------------------
// search
// ---------------------------------------------------------------------------

func cmdSearch() {
	fs := flag.NewFlagSet("search", flag.ExitOnError)
	email := fs.String("email", "", "email address to search for")
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	seeds := fs.String("seeds", "", "additional comma-separated seed node URLs")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	query := *email
	if query == "" && len(fs.Args()) > 0 {
		query = fs.Args()[0]
	}
	if query == "" {
		fmt.Fprintln(os.Stderr, "usage: gpgchain search --email <email> [--server <url>]")
		os.Exit(1)
	}

	seedList := []string{strings.TrimRight(*serverURL, "/")}
	if *seeds != "" {
		for _, s := range strings.Split(*seeds, ",") {
			if u := strings.TrimSpace(s); u != "" {
				seedList = append(seedList, u)
			}
		}
	}

	result := discovery.FindBlocksByEmail(query, seedList, 20, 5*time.Second)
	if !result.Found() {
		fmt.Printf("No blocks found for %q (tried %d nodes)\n", query, result.NodesTried)
		return
	}

	fmt.Printf("Found %d block(s) for %q (tried %d nodes):\n\n", len(result.Blocks), query, result.NodesTried)
	for _, nb := range result.Blocks {
		fmt.Printf("Node: %s\n", nb.NodeURL)
		printBlock(map[string]any{
			"fingerprint":      nb.Block.Fingerprint,
			"hash":             nb.Block.Hash,
			"uids":             toAny(nb.Block.UIDs),
			"submit_timestamp": float64(nb.Block.SubmitTimestamp),
			"revoked":          nb.Block.Revoked,
			"sig_chain":        []any{},
		})
		fmt.Println()
	}
}

func toAny(ss []string) []any {
	out := make([]any, len(ss))
	for i, s := range ss {
		out[i] = s
	}
	return out
}

// ---------------------------------------------------------------------------
// verify
// ---------------------------------------------------------------------------

func cmdVerify() {
	fs := flag.NewFlagSet("verify", flag.ExitOnError)
	serverURL := fs.String("server", envOr("GPGCHAIN_SERVER", "http://localhost:8080"), "node URL")
	fs.Parse(os.Args[2:]) //nolint:errcheck

	rawBody, status, err := httpGet(strings.TrimRight(*serverURL, "/") + "/blocks")
	if err != nil {
		die("request failed: %v", err)
	}
	if status != 200 {
		die("server returned %d", status)
	}

	var blocks []*chain.Block
	if err := json.Unmarshal(rawBody, &blocks); err != nil {
		die("invalid response: %v", err)
	}

	// Build fingerprint → ArmoredKey map for looking up signer keys.
	keyMap := map[string]string{}
	for _, b := range blocks {
		keyMap[strings.ToUpper(b.Fingerprint)] = b.ArmoredKey
	}

	totalFailures := 0
	for _, b := range blocks {
		fp := strings.ToUpper(b.Fingerprint)
		blockFailures := 0

		// Verify self-sig.
		payload := gpg.SubmitPayload(fp, b.ArmoredKey, b.SubmitTimestamp)
		if !gpg.VerifyDetachedSig(payload, b.SelfSig, b.ArmoredKey) {
			fmt.Printf("FAIL  %s  self_sig verification failed\n", fp)
			blockFailures++
		}

		// Verify revocation sig if present.
		if b.Revoked && b.RevocationSig != "" {
			rp := gpg.RevokePayload(fp, b.Hash)
			if !gpg.VerifyDetachedSig(rp, b.RevocationSig, b.ArmoredKey) {
				fmt.Printf("FAIL  %s  revocation_sig verification failed\n", fp)
				blockFailures++
			}
		}

		// Verify sig chain.
		prevHash := b.Hash
		for i, e := range b.SigEntries {
			// Hash chain integrity.
			expectedHash := chain.ComputeSigEntryHash(e.PrevHash, e.SignerFingerprint, e.Sig, e.Timestamp)
			if !strings.EqualFold(expectedHash, e.Hash) {
				fmt.Printf("FAIL  %s  sig_chain[%d] hash mismatch\n", fp, i)
				blockFailures++
				continue
			}
			if !strings.EqualFold(e.PrevHash, prevHash) {
				fmt.Printf("FAIL  %s  sig_chain[%d] prev_hash broken\n", fp, i)
				blockFailures++
				continue
			}
			prevHash = e.Hash

			// Signature verification.
			signerKey := e.SignerArmoredKey
			if signerKey == "" {
				signerKey = keyMap[strings.ToUpper(e.SignerFingerprint)]
			}
			if signerKey == "" {
				fmt.Printf("WARN  %s  sig_chain[%d] signer %s key not available for verification\n",
					fp, i, e.SignerFingerprint)
				continue
			}
			tp := gpg.TrustPayload(b.Hash, strings.ToUpper(e.SignerFingerprint), e.Timestamp)
			if !gpg.VerifyDetachedSig(tp, e.Sig, signerKey) {
				fmt.Printf("FAIL  %s  sig_chain[%d] sig verification failed (signer %s)\n",
					fp, i, e.SignerFingerprint)
				blockFailures++
			}
		}

		if blockFailures == 0 {
			fmt.Printf("OK    %s  (%d sigs)\n", fp, len(b.SigEntries))
		}
		totalFailures += blockFailures
	}
	failures := totalFailures

	if failures > 0 {
		fmt.Printf("\n%d verification failure(s)\n", failures)
		os.Exit(1)
	} else {
		fmt.Printf("\nAll %d block(s) verified OK\n", len(blocks))
	}
}
