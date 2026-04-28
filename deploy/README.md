# Deploying GPG Chain

Two CloudFormation stacks with separate lifecycles:

| Stack | Template | Lifecycle |
|---|---|---|
| DNS | `dns.yaml` | Permanent — deploy once, leave running |
| Node | `cloudformation.yaml` | On-demand — start and stop as needed |

The DNS stack owns the Elastic IP and Route 53 record. The node stack owns the EC2 instance. Stopping the node costs nothing beyond the Elastic IP (~£0.75/month) and S3 storage (negligible). Your block store data persists in S3 between deployments.

---

## Prerequisites

- AWS CLI configured with a named profile
- A Route 53 hosted zone for your domain
- An EC2 key pair in your target region
- `jq` installed locally

---

## First deployment

### 1. Deploy the DNS stack

```bash
./scripts/deploy-dns.sh \
    --domain keys.example.com \
    --profile myprofile
```

The script looks up the Route 53 hosted zone automatically by walking up the domain hierarchy.
Pass `--hosted-zone-id` explicitly if the lookup fails or you have multiple zones for the same domain.

This creates an Elastic IP and a Route 53 A record. Run once and leave it running.

### 2. Deploy the node

```bash
./scripts/deploy-node.sh \
    --domain demo.gpgchain.co.uk \
    --profile myprofile \
    --allow-all-domains \
    --key-name my-key \
    --vpc-id vpc-xxxx \
    --subnet-id subnet-xxxx \
    --letsencrypt-email you@example.com
```

The node will be live at `https://demo.gpgchain.co.uk` once DNS has propagated and Caddy has obtained the TLS certificate (typically 2–5 minutes).

### 3. Check status

```bash
./scripts/node-status.sh \
    --domain demo.gpgchain.co.uk \
    --profile myprofile
```

---

## Stopping and restarting

```bash
# Stop (deletes EC2 instance — data and DNS are preserved)
./scripts/stop-node.sh \
    --domain demo.gpgchain.co.uk \
    --profile myprofile

# Start again (data is immediately available from S3)
./scripts/deploy-node.sh \
    --domain demo.gpgchain.co.uk \
    --profile myprofile \
    --allow-all-domains \
    --key-name my-key \
    --vpc-id vpc-xxxx \
    --subnet-id subnet-xxxx
```

---

## Scripts

| Script | Description |
|---|---|
| `scripts/deploy-dns.sh` | Deploy the DNS stack (run once) |
| `scripts/deploy-node.sh` | Deploy or update the node stack |
| `scripts/stop-node.sh` | Delete the node stack |
| `scripts/node-status.sh` | Show stack state, instance state, DNS resolution, and live HTTPS check |

All scripts accept `--help` for full flag documentation.

---

## Parameters

### deploy-dns.sh

| Flag | Required | Description |
|---|---|---|
| `--domain` | yes | FQDN for the node |
| `--profile` | yes | AWS CLI profile |
| `--hosted-zone-id` | no | Route 53 hosted zone ID — looked up automatically if omitted |
| `--ttl` | no | DNS TTL in seconds (default: 300) |
| `--stack-prefix` | no | Stack name prefix (default: gpgchain) |
| `--region` | no | AWS region (default: profile default) |

### deploy-node.sh

| Flag | Required | Description |
|---|---|---|
| `--domain` | yes | FQDN matching the DNS stack |
| `--profile` | yes | AWS CLI profile |
| `--key-name` | yes | EC2 key pair name |
| `--vpc-id` | yes | VPC to deploy into |
| `--subnet-id` | yes | Public subnet ID |
| `--allow-all-domains` | * | Accept keys from any email domain |
| `--allowed-domains` | * | Comma-separated allowed domains |
| `--letsencrypt-email` | no | Email for cert expiry notifications |
| `--instance-type` | no | EC2 instance type (default: t3.small) |
| `--bootstrap-peers` | no | Comma-separated peer node URLs |
| `--s3-bucket` | no | Existing S3 bucket (default: auto-create) |
| `--ssh-cidr` | no | CIDR for SSH access (default: 0.0.0.0/0) |
| `--stack-prefix` | no | Stack name prefix (default: gpgchain) |
| `--region` | no | AWS region (default: profile default) |

\* One of `--allow-all-domains` or `--allowed-domains` is required.

---

## Cost estimate

| State | Cost |
|---|---|
| Node running (t3.small) | ~£1/week |
| Node stopped | ~£0.75/month (Elastic IP) + negligible S3 |

See `docs/operator-guide.md` for more detail.
