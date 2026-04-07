# TODO

Tasks are ordered by dependency. Tests are written before implementations.
Format: `[ ] CODE — description`

---

## S — Setup

- [ ] S01 — Create full directory structure (`spec/`, `implementations/python/`, `implementations/go/`, `tests/`, `scripts/`, `docs/`)
- [ ] S02 — Python: `pyproject.toml`, `requirements.txt`, stub `node.py` + `client.py`
- [ ] S03 — Python: create all package skeletons (`__init__.py` in every module); all API routes return 501
- [ ] S04 — Go: `go.mod` with dependencies; stub `cmd/node/main.go` + `cmd/client/main.go`; all routes return 501
- [ ] S05 — Go: create all package skeletons; verify `go build ./...` succeeds
- [ ] S06 — Tests: `tests/environment.py`, `tests/support/client.py`, `tests/support/gpg_helper.py`, `tests/requirements.txt`
- [ ] S07 — Scripts: `scripts/build.sh`, `scripts/cluster.sh`, `scripts/clean.sh` (stubs)
- [ ] S08 — Verify: both servers start and return 501; `behave tests/` runs with undefined steps

---

## SP — Specification

- [ ] SP01 — `spec/data-model.md` — Block and SigEntry fields, hash computation rules, file naming convention
- [ ] SP02 — `spec/payloads.md` — SUBMIT, TRUST, REVOKE binary payload formats with worked examples
- [ ] SP03 — `spec/trust.md` — multi-hop BFS algorithm, scoring, cycle detection, cross-ledger traversal
- [ ] SP04 — `spec/p2p.md` — gossip, bounded fanout, sync, peer exchange, cross-validation
- [ ] SP05 — `spec/openapi.yaml` — all public + peer endpoints, request/response schemas, error codes

---

## D — Data Model

- [ ] D01 — Python: `Block` + `SigEntry` dataclasses in `chain/models.py` (fields only, no logic)
- [ ] D02 — Python: block hash computation in `chain/hashing.py`; unit test
- [ ] D03 — Python: SigEntry hash computation; unit test
- [ ] D04 — Go: `Block` + `SigEntry` structs in `internal/chain/block.go`
- [ ] D05 — Go: block + SigEntry hash computation; unit test

---

## G — GPG Helpers

- [ ] G01 — Python: parse armored key, extract fingerprint + UIDs; unit test
- [ ] G02 — Python: enforce minimum key strength (RSA ≥ 2048, Ed25519 ok, DSA-1024 reject); unit test
- [ ] G03 — Python: construct SUBMIT binary payload; unit test
- [ ] G04 — Python: construct TRUST binary payload; unit test
- [ ] G05 — Python: construct REVOKE binary payload; unit test
- [ ] G06 — Python: verify detached GPG sig against armored public key; unit test
- [ ] G07 — Go: G01–G06 equivalent; unit tests

---

## ST — Store

- [ ] ST01 — Python: `Store` protocol in `store/protocol.py`
- [ ] ST02 — Python: `MemoryStore` (tests only); unit test
- [ ] ST03 — Python: `DirStore` path derivation + atomic write helper; unit test
- [ ] ST04 — Python: `DirStore.add(block)` — write `<fp>.block.json`; reject duplicate; unit test
- [ ] ST05 — Python: `DirStore.get(fp)` — load from disk, reconstruct sig chain via PrevHash; unit test
- [ ] ST06 — Python: `DirStore.get(fp)` — LRU cache layer; unit test (cache hit, cache miss, eviction)
- [ ] ST07 — Python: `DirStore.add_sig(fp, entry)` — write `<fp>.sig.<hash>.json`; update cache; unit test
- [ ] ST08 — Python: `DirStore.revoke(fp, sig)` — write `<fp>.revoke.json`; update cache; unit test
- [ ] ST09 — Python: `DirStore.all()` — directory walk; unit test
- [ ] ST10 — Python: `DirStore.hashes()` — return `{fp: sig_chain_head}` from filenames only; unit test
- [ ] ST11 — Go: `Store` interface in `internal/store/store.go`
- [ ] ST12 — Go: `MemoryStore` (tests only); unit test
- [ ] ST13 — Go: SQLite schema + `modernc.org/sqlite` setup; migration on open
- [ ] ST14 — Go: `SQLiteStore.Add` + `Get`; unit test
- [ ] ST15 — Go: `SQLiteStore.AddSig` + `Revoke`; unit test
- [ ] ST16 — Go: `SQLiteStore.All` + `Hashes`; unit test

---

## F01 — Submit a Key

- [ ] F01-T1 — Write `tests/features/adding-keys.feature` (all scenarios)
- [ ] F01-T2 — Write step definitions for adding-keys
- [ ] F01-P1 — Python: `POST /block` — verify self-sig, enforce key strength, store block
- [ ] F01-P2 — Python: `GET /block/:fingerprint` + `GET /blocks`
- [ ] F01-P3 — Python: all adding-keys scenarios green
- [ ] F01-G1 — Go: `POST /block` + `GET` routes
- [ ] F01-G2 — Go: all adding-keys scenarios green
- [ ] F01-C1 — CLI: `gpgchain add` (Python + Go)

---

## F02 — Domain Allowlist

- [ ] F02-T1 — Write `tests/features/domain-allowlist.feature`
- [ ] F02-T2 — Write step definitions
- [ ] F02-P1 — Python: domain config (`--domains`, `--allow-all-domains`); enforce on `POST /block` + `POST /p2p/block`
- [ ] F02-P2 — Python: all domain-allowlist scenarios green
- [ ] F02-G1 — Go: equivalent
- [ ] F02-G2 — Go: all domain-allowlist scenarios green

---

## F03 — Search

- [ ] F03-T1 — Write `tests/features/search.feature`
- [ ] F03-T2 — Write step definitions
- [ ] F03-P1 — Python: `GET /search?q=` — substring match against UIDs
- [ ] F03-P2 — Python: all search scenarios green
- [ ] F03-G1 — Go: `GET /search?q=`
- [ ] F03-G2 — Go: all search scenarios green
- [ ] F03-C1 — CLI: `gpgchain search` (Python + Go)

---

## F04 — Sign a Key (on-ledger)

- [ ] F04-T1 — Write `tests/features/signing-keys.feature`
- [ ] F04-T2 — Write step definitions
- [ ] F04-P1 — Python: `POST /block/:fp/sign` — verify signer on ledger, verify TRUST payload sig, append SigEntry
- [ ] F04-P2 — Python: all signing-keys scenarios green
- [ ] F04-G1 — Go: equivalent
- [ ] F04-G2 — Go: all signing-keys scenarios green
- [ ] F04-C1 — CLI: `gpgchain sign` (Python + Go)

---

## F05 — Off-Ledger Signatures

- [ ] F05-T1 — Write `tests/features/off-ledger-signatures.feature`
- [ ] F05-T2 — Write step definitions
- [ ] F05-P1 — Python: extend `POST /block/:fp/sign` — accept `signer_armored_key` + `source_node`; verify inline; store in SigEntry
- [ ] F05-P2 — Python: all off-ledger scenarios green
- [ ] F05-G1 — Go: equivalent
- [ ] F05-G2 — Go: all off-ledger scenarios green

---

## F06 — Revocation

- [ ] F06-T1 — Write `tests/features/revocation.feature`
- [ ] F06-T2 — Write step definitions
- [ ] F06-P1 — Python: `POST /block/:fp/revoke` — verify REVOKE payload sig against block's own key; write revoke file
- [ ] F06-P2 — Python: all revocation scenarios green
- [ ] F06-G1 — Go: equivalent
- [ ] F06-G2 — Go: all revocation scenarios green
- [ ] F06-C1 — CLI: `gpgchain revoke` (Python + Go)

---

## F07 — Trust Evaluation

- [ ] F07-T1 — Write `tests/features/trust.feature`
- [ ] F07-T2 — Write step definitions
- [ ] F07-P1 — Python: `trust/graph.py` — build adjacency map from ledger
- [ ] F07-P2 — Python: BFS scorer with depth limit + cycle detection
- [ ] F07-P3 — Python: `trusted_set()` helper
- [ ] F07-P4 — Python: all trust scenarios green
- [ ] F07-G1 — Go: `internal/trust/` — graph, BFS scorer, cycle detection, trusted set
- [ ] F07-G2 — Go: all trust scenarios green
- [ ] F07-C1 — CLI: `gpgchain check` + `gpgchain list --min-trust` (Python + Go)

---

## F08 — Show + Verify

- [ ] F08-T1 — Write `tests/features/show-verify.feature`
- [ ] F08-T2 — Write step definitions
- [ ] F08-P1 — Python: `GET /block/:fp` returns full block with sig chain; client-side `verify` logic
- [ ] F08-P2 — Python: all show-verify scenarios green
- [ ] F08-G1 — Go: equivalent
- [ ] F08-G2 — Go: all show-verify scenarios green
- [ ] F08-C1 — CLI: `gpgchain show` + `gpgchain verify` (Python + Go)

---

## F09 — Well-Known Endpoint

- [ ] F09-T1 — Write `tests/features/cross-ledger.feature` (well-known section only)
- [ ] F09-T2 — Write step definitions
- [ ] F09-P1 — Python: `GET /.well-known/gpgchain.json` — return node URL + served domains + peers
- [ ] F09-P2 — Python: green
- [ ] F09-G1 — Go: equivalent
- [ ] F09-G2 — Go: green

---

## F10 — Cross-Ledger Trust Traversal

- [ ] F10-T1 — Add cross-ledger trust scenarios to `cross-ledger.feature`
- [ ] F10-T2 — Write step definitions (requires two independent nodes)
- [ ] F10-P1 — Python: extend `trust/graph.py` — follow `source_node` URLs to fetch remote blocks; continue BFS; respect depth limit across boundaries
- [ ] F10-P2 — Python: all cross-ledger scenarios green
- [ ] F10-G1 — Go: equivalent
- [ ] F10-G2 — Go: all cross-ledger scenarios green

---

## F11 — P2P Peer Registration

- [ ] F11-T1 — Write `tests/features/p2p-peers.feature`
- [ ] F11-T2 — Write step definitions
- [ ] F11-P1 — Python: `GET /peers` + `POST /peers` — reciprocal check, private IP rejection, peer cap
- [ ] F11-P2 — Python: all p2p-peers scenarios green
- [ ] F11-G1 — Go: equivalent
- [ ] F11-G2 — Go: all p2p-peers scenarios green

---

## F12 — P2P Gossip

- [ ] F12-T1 — Write `tests/features/p2p-gossip.feature`
- [ ] F12-T2 — Write step definitions
- [ ] F12-P1 — Python: gossip on block/sig/revoke; bounded fanout K=3; seen-set
- [ ] F12-P2 — Python: `POST /p2p/block`, `POST /p2p/sign`, `POST /p2p/revoke`
- [ ] F12-P3 — Python: all gossip scenarios green
- [ ] F12-G1 — Go: equivalent
- [ ] F12-G2 — Go: all gossip scenarios green

---

## F13 — P2P Sync

- [ ] F13-T1 — Write `tests/features/p2p-sync.feature`
- [ ] F13-T2 — Write step definitions
- [ ] F13-P1 — Python: `GET /p2p/hashes` — return `{fp: sig_chain_head}` map
- [ ] F13-P2 — Python: `GET /p2p/block/:hash` — return single block
- [ ] F13-P3 — Python: sync-on-connect — diff hashes with peers, fetch missing
- [ ] F13-P4 — Python: all sync scenarios green
- [ ] F13-G1 — Go: equivalent
- [ ] F13-G2 — Go: all sync scenarios green

---

## F14 — P2P Cross-Validation

- [ ] F14-T1 — Write `tests/features/p2p-cross-validation.feature`
- [ ] F14-T2 — Write step definitions
- [ ] F14-P1 — Python: periodic diff of `{fp: sig_chain_head}` across peers; warn on mismatch; fetch longer chain
- [ ] F14-P2 — Python: all cross-validation scenarios green
- [ ] F14-G1 — Go: equivalent
- [ ] F14-G2 — Go: all cross-validation scenarios green

---

## F15 — Interoperability

- [ ] F15-T1 — Write `tests/features/interop.feature`
- [ ] F15-T2 — Write step definitions (requires mixed cluster)
- [ ] F15-01 — Full feature suite against Python node: all green
- [ ] F15-02 — Full feature suite against Go node: all green
- [ ] F15-03 — P2P + interop features against mixed cluster (--go 2 --python 2): all green
- [ ] F15-04 — Scripts: `cluster.sh` fully functional with status, start, stop

---

## Resolved Design Decisions
- Trust decisions → always client-side; server has no trust concept whatsoever
- Language → Python (reference), Go (production); both pass the same feature suite
- Test runner → `behave` with Gherkin; `.feature` files portable to any Cucumber runner
- Python store → directory tree (2+2 prefix, configurable); immutable files; LRU cache (default 128); zero-cost rehydration
- Go store → SQLite via `modernc.org/sqlite` (pure Go, no CGo)
- P2P → content-addressed DAG; no longest-chain consensus; bounded fanout K=3
- Submission → self-signature required; timestamp in signed payload, set by client
- Signing payloads → typed binary with domain separation and version prefix
- Signature integrity → per-block linked chain anchored to block hash; SigChainHead in peer hash exchange
- Off-ledger signatures → inline armored key + source_node URL; same key strength rules apply
- Cross-ledger discovery → `/.well-known/gpgchain.json`; client-initiated traversal only
- Domain allowlist → empty = accept nothing; explicit allow_all; any matching UID passes; applies to gossip
- Eclipse/SSRF → reciprocal check; private IP rejection; peer list cap
- Key strength → RSA ≥ 2048; Ed25519 preferred; DSA-1024 rejected
