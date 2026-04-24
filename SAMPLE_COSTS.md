# Sample Costs

All prices are approximate, in USD, and based on AWS us-east-1 on-demand rates as of early 2026.
Prices vary by region (eu-west-2 / London is typically 10–15% higher) and change over time.
Use the [AWS Pricing Calculator](https://calculator.aws) for current figures.

---

## Storage: how big is each object?

### Block (one per key)

| Key type | Armored key | Self-sig | Total JSON |
|---|---|---|---|
| Ed25519 | ~800 bytes | ~120 bytes | ~1.2 KB |
| RSA-2048 | ~1,800 bytes | ~370 bytes | ~2.4 KB |
| RSA-4096 | ~3,300 bytes | ~370 bytes | ~3.9 KB |

### SigEntry (one per trust signature)

| Signer type | Notes | Size |
|---|---|---|
| On-ledger signer | Two 64-char hashes, fingerprint, base64 sig, timestamp | ~0.5 KB |
| Off-ledger Ed25519 | As above + signer's armored public key | ~1.4 KB |
| Off-ledger RSA-2048 | As above + signer's armored public key | ~2.5 KB |

In a typical public web-of-trust deployment, most signers will be on-ledger. The calculations
below use **0.5 KB per signature** as the baseline.

---

## Storage cost: per 1,000 signatures

| Signatures | Storage | S3 cost/month | One-time write cost |
|---|---|---|---|
| 1,000 | 0.5 MB | $0.00 | $0.005 |
| 10,000 | 5 MB | $0.00 | $0.05 |
| 100,000 | 50 MB | $0.001 | $0.50 |
| 1,000,000 | 500 MB | $0.01 | $5.00 |
| 10,000,000 | 5 GB | $0.12 | $50.00 |

**The storage cost per 1,000 signatures is effectively $0.00/month.**
The write cost (one-time, at submission) is $0.005 per 1,000 signatures.

Even at 1 million signatures — more than any realistic public keyserver — the ongoing
S3 storage cost is about **one cent per month**.

---

## Scenario: "thousands of people sign my key"

If your key accumulates signatures over time:

| Signatures on your key | Storage used | S3 cost/month |
|---|---|---|
| 100 | 50 KB | $0.00 |
| 1,000 | 500 KB | $0.00 |
| 10,000 | 5 MB | $0.00 |
| 100,000 | 50 MB | $0.001 |

Storage is not a concern at any realistic scale. The cost that dominates is the EC2 instance.

---

## S3 request costs

The Python store reads a block by listing its directory (1 LIST) then fetching each sig file
(1 GET per signature). The LRU cache (default 128 blocks) means frequently-read blocks rarely
touch S3 after the first load.

| Operation | S3 cost |
|---|---|
| Write one signature | $0.000005 (1 PUT) |
| Read a block with 100 sigs (cache miss) | $0.000045 (1 LIST + 100 GETs) |
| Read a block with 1,000 sigs (cache miss) | $0.000405 (1 LIST + 1,000 GETs) |
| Read a cached block | $0.00 |

For a lightly used demo node serving a few hundred requests per day, S3 request costs
are well under **$0.10/month**.

---

## EC2 running costs

The demo stack uses the Python/S3 backend on a **t3.small** (2 vCPU, 2 GB RAM).

| | t3.small (on-demand) | t3.small (1-yr reserved) |
|---|---|---|
| Hourly | $0.0208 | $0.013 |
| Daily | $0.50 | $0.31 |
| Weekly | $3.50 | $2.19 |
| Monthly | $15.18 | $9.49 |

---

## Elastic IP cost

The Elastic IP lives in the DNS stack and persists when the node is stopped.

| State | Cost |
|---|---|
| Associated with a running instance | $0.00 |
| Unassociated (node stack deleted) | $0.005/hour = **$3.60/month** |

---

## Data transfer

Outbound data transfer from EC2 to the internet is charged at $0.09/GB.

A typical API response (one block + 50 signatures) is roughly 30 KB.
At 10,000 requests/month that is ~300 MB outbound — about **$0.027/month**.

For a lightly used demo node, data transfer is negligible.

---

## Scenario summaries

### Demo node — personal keyserver, running full-time

| Component | Monthly cost |
|---|---|
| t3.small EC2 (on-demand) | $15.18 |
| S3 storage (10,000 keys, 50 sigs each) | $0.01 |
| S3 requests (light traffic) | $0.05 |
| Data transfer (light traffic) | $0.03 |
| Elastic IP (always associated) | $0.00 |
| **Total** | **~$15.30/month** |

### Demo node — stopped when not in use (8 hours/day, 5 days/week)

Approximately 174 running hours/month (vs. 730 always-on).

| Component | Monthly cost |
|---|---|
| t3.small EC2 (~174 hrs) | $3.62 |
| S3 storage | $0.01 |
| S3 requests | $0.02 |
| Elastic IP (unassociated ~556 hrs) | $2.78 |
| **Total** | **~$6.40/month** |

### Demo node — deployed for a week-long event, then stopped

| Component | Cost |
|---|---|
| t3.small EC2 (168 hrs) | $3.50 |
| S3 storage (retained, ongoing) | $0.01/month |
| Elastic IP (unassociated rest of month) | $2.78 |
| **Total for that month** | **~$6.30** |

### Small organisation — 100 users, always-on

Assumes ~500 keys, ~5,000 signatures, moderate API traffic.

| Component | Monthly cost |
|---|---|
| t3.small EC2 | $15.18 |
| S3 storage (2.5 MB) | $0.00 |
| S3 requests + data transfer | $0.50 |
| Elastic IP | $0.00 |
| **Total** | **~$15.70/month** |

---

## Key takeaway

**S3 storage cost per 1,000 signatures: effectively $0.00/month.**

The EC2 instance ($15/month always-on, or $3.50/week) and the Elastic IP when
idle ($3.60/month) are the only costs worth planning around. S3 storage and
request costs are noise at any realistic keyserver scale.

To minimise cost: use the stop/start workflow (`scripts/stop-node.sh` /
`scripts/deploy-node.sh`) to run the instance only when needed. The DNS record
and all data persist between deployments.
