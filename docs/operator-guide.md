# Operator Guide

This guide covers running a GPG Chain node in production: configuration, domain scoping, peering, persistence, security hardening, and monitoring.

---

## Choosing an implementation

**Python** (`implementations/python/`) — well-suited for low-traffic deployments and development. Simple to deploy with a WSGI/ASGI server (Uvicorn, Gunicorn). File-system store; no external database dependency.

**Go** (`implementations/go/`) — recommended for production. Statically linked binary, low memory footprint, SQLite store with ACID transactions, concurrent gossip via goroutines.

Both expose the same API and pass the same test suite. You can run a mixed cluster.

---

## Building the Go binary

```bash
./scripts/build.sh
```

The binary is written to `implementations/go/cmd/node/node`. Copy it anywhere on your PATH.

---

## Basic configuration

### Go node

```bash
node \
    --addr 0.0.0.0:8080 \
    --store-dir /var/lib/gpgchain \
    --node-url https://keys.example.com \
    --domains example.com,subsidiary.example.com
```

| Flag | Env var | Default | Purpose |
|---|---|---|---|
| `--addr` | — | `0.0.0.0:8080` | Listen address |
| `--store-dir` | `GPGCHAIN_STORE_DIR` | `./data` | SQLite database directory |
| `--node-url` | `GPGCHAIN_NODE_URL` | (empty) | This node's public URL (returned by `/.well-known/`) |
| `--domains` | `GPGCHAIN_DOMAINS` | (empty) | Comma-separated allowed email domains |
| `--allow-all-domains` | `GPGCHAIN_ALLOW_ALL=true` | off | Accept keys from any email domain |
| `--peers` | — | (empty) | Bootstrap peer URLs (comma-separated) |
| `--allow-private-peers` | `GPGCHAIN_ALLOW_PRIVATE_PEERS=true` | off | Skip private IP rejection (containers only) |
| `--max-peers` | — | 50 | Maximum peer list size |
| `--gossip-fanout` | — | 3 | Number of peers to forward each event to |

### Python node

```bash
python implementations/python/node.py \
    --addr 0.0.0.0:8080 \
    --store-dir /var/lib/gpgchain \
    --node-url https://keys.example.com \
    --domains example.com,subsidiary.example.com
```

Python node flags are the same as Go. See `python node.py --help` for the full list.

---

## Domain configuration

Every node must declare which email domains it accepts. This is an organisational scoping mechanism — it prevents your node from accumulating keys outside your organisation.

### Accept specific domains

```bash
--domains example.com,subsidiary.example.com
```

Only keys whose UIDs include an email address in one of these domains will be accepted.

### Accept all domains (development/open nodes)

```bash
--allow-all-domains
```

Required if the domain list is empty and you want to accept any key. Without this flag, an empty domain list means the node accepts nothing.

### Domain filtering applies to gossip

When a peer forwards a block, the node applies the same domain filter. A node will not store or forward keys outside its allowlist regardless of where they came from. Two nodes with non-overlapping domain configs form isolated ledgers that speak the same protocol.

---

## Peering

### Bootstrap peers

Provide initial peers at startup:

```bash
--peers https://keys.partner.org,https://keys.other.example.com
```

The node registers with each peer at startup and initiates sync.

### Peer registration

When a client or peer calls `POST /peers`, the node:

1. Resolves the address to an IP
2. Rejects private/loopback IPs (e.g. `10.x.x.x`, `192.168.x.x`, `127.x.x.x`, `::1`) unless `--allow-private-peers` is set
3. Performs a reciprocal reachability check (`GET <addr>/peers`)
4. Accepts the peer if the check succeeds and the peer list is below the cap

Only set `--allow-private-peers` in container environments where private IPs are legitimate. Never use it on a public-facing node.

### Peer list cap

The peer list is capped at `--max-peers` (default 50). New peers beyond this limit are rejected with a 503. Operate well below this limit to leave room for organic peer discovery.

---

## Persistence

### Go: SQLite

The Go node stores everything in a SQLite database at `<store-dir>/gpgchain.db`. The database uses WAL mode and ACID transactions. No separate backup of an in-memory index is needed — the database is the store.

**Backup:**
```bash
sqlite3 /var/lib/gpgchain/gpgchain.db ".backup /backup/gpgchain-$(date +%Y%m%d).db"
```

**Restore:** Copy the database file to `<store-dir>/gpgchain.db` and restart the node.

### Python: directory tree

The Python node stores one JSON file per block, one per SigEntry, and one per revocation under `<store-dir>/`. The directory tree is self-describing; no index is needed.

**Backup:**
```bash
rsync -a /var/lib/gpgchain/ /backup/gpgchain-$(date +%Y%m%d)/
```

**Restore:** Copy the directory tree to `<store-dir>/` and restart the node.

---

## Running as a service

### systemd unit (Go node)

```ini
[Unit]
Description=GPG Chain node
After=network.target

[Service]
Type=simple
User=gpgchain
ExecStart=/usr/local/bin/gpgchain-node \
    --addr 0.0.0.0:8080 \
    --store-dir /var/lib/gpgchain \
    --node-url https://keys.example.com \
    --domains example.com
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /bin/false gpgchain
sudo mkdir -p /var/lib/gpgchain
sudo chown gpgchain:gpgchain /var/lib/gpgchain
sudo systemctl enable --now gpgchain
```

### Docker (Go node)

```dockerfile
FROM scratch
COPY node /node
ENTRYPOINT ["/node"]
```

```bash
docker run -d \
    -p 8080:8080 \
    -v /var/lib/gpgchain:/data \
    -e GPGCHAIN_STORE_DIR=/data \
    -e GPGCHAIN_NODE_URL=https://keys.example.com \
    -e GPGCHAIN_DOMAINS=example.com \
    gpgchain-node
```

---

## TLS / reverse proxy

The node speaks plain HTTP. Place it behind a TLS-terminating reverse proxy (nginx, Caddy, Traefik) for HTTPS.

Example nginx config:

```nginx
server {
    listen 443 ssl;
    server_name keys.example.com;

    ssl_certificate     /etc/ssl/certs/keys.example.com.crt;
    ssl_certificate_key /etc/ssl/private/keys.example.com.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Health checking

The node does not expose a dedicated `/health` endpoint. Use:

```bash
curl http://localhost:8080/peers          # should return []  or a JSON array
curl http://localhost:8080/.well-known/gpgchain.json
```

A successful JSON response indicates the node is up and the HTTP layer is functioning.

For a load balancer health check, `GET /peers` is appropriate (200 + JSON, fast, no database load).

---

## Security hardening

**Run as a non-root user.** The node requires no elevated privileges. Create a dedicated `gpgchain` system user.

**Restrict the store directory.** Only the `gpgchain` user should have read/write access to `<store-dir>`. Mode `0700` is appropriate.

**Do not expose the P2P endpoints publicly.** The `/p2p/*` endpoints are for inter-node communication. If your network topology allows it, restrict access to these paths to known peer IP ranges via your reverse proxy or firewall.

**Set `--node-url` correctly.** The `node_url` field in `/.well-known/gpgchain.json` is used by other nodes and clients for cross-ledger discovery. It must be your node's reachable public URL.

**Do not use `--allow-private-peers` on public nodes.** This flag is for container deployments with controlled bridge networks only.

---

## Monitoring

### Key metrics to watch

| Metric | How to check | What to look for |
|---|---|---|
| Block count | `curl /p2p/hashes \| jq length` | Growing steadily; should match peers |
| Peer count | `curl /peers \| jq length` | Non-zero; growing over time |
| Cross-validation discrepancies | Node logs | Any `WARN` about hash mismatches |
| Response latency | Your reverse proxy logs | Elevated latency on `/blocks` suggests store pressure |

### Cross-validation

Nodes log discrepancies found during cross-validation at `WARN` level. A discrepancy means one node has a longer sig chain for a block than another — either because gossip is slow or because a node is censoring signatures.

To check manually:

```bash
# Compare sig chain heads between two nodes
diff \
    <(curl -s http://node-a:8080/p2p/hashes | jq -S .) \
    <(curl -s http://node-b:8080/p2p/hashes | jq -S .)
```

Any difference means one node has data the other does not.

---

## Multi-node cluster

Use `./scripts/cluster.sh` to manage a local mixed cluster for testing:

```bash
# Start 2 Go nodes + 1 Python node
./scripts/cluster.sh start --go 2 --python 1

# Check status
./scripts/cluster.sh status

# Stop all
./scripts/cluster.sh stop
```

The script wires all nodes together as peers and allocates ports starting from 8080.

For a production cluster, peer your nodes explicitly at startup with `--peers`, and let the gossip protocol distribute new blocks and signatures automatically.
