#!/usr/bin/env bash
# Deploy (or update) the GPG Chain node stack.
# Requires the DNS stack to be running first (deploy-dns.sh).
# Safe to run repeatedly — CloudFormation is idempotent.
set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") --domain DOMAIN --profile PROFILE --key-name KEY --vpc-id VPC --subnet-id SUBNET [options]

Required:
  --domain DOMAIN           FQDN matching the DNS stack (e.g. demo.gpgchain.co.uk)
  --profile PROFILE         AWS CLI profile name
  --key-name KEY            EC2 key pair name (must exist in the target region)
  --vpc-id VPC              VPC ID to deploy into
  --subnet-id SUBNET        Public subnet ID (must have internet access)

Optional:
  --stack-prefix PREFIX     Stack name prefix (default: gpgchain)
  --instance-type TYPE      EC2 instance type (default: t3.small)
  --allow-all-domains       Accept keys from any email domain
  --allowed-domains DOMAINS Comma-separated allowed email domains
  --letsencrypt-email EMAIL  Email for Let's Encrypt notifications
  --bootstrap-peers PEERS   Comma-separated peer node URLs
  --ssh-cidr CIDR           CIDR for SSH access (default: 0.0.0.0/0)
  --s3-bucket BUCKET        Existing S3 bucket name (default: auto-create)
  --region REGION           AWS region (default: profile default)
  -h, --help
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

DOMAIN="" PROFILE="" KEY_NAME="" VPC_ID="" SUBNET_ID=""
STACK_PREFIX="gpgchain" INSTANCE_TYPE="t3.small"
ALLOW_ALL_DOMAINS="false" ALLOWED_DOMAINS="" LETSENCRYPT_EMAIL=""
BOOTSTRAP_PEERS="" SSH_CIDR="0.0.0.0/0" S3_BUCKET="" REGION=""

[[ $# -eq 0 ]] && { usage; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)             DOMAIN="$2";             shift 2 ;;
        --profile)            PROFILE="$2";            shift 2 ;;
        --key-name)           KEY_NAME="$2";           shift 2 ;;
        --vpc-id)             VPC_ID="$2";             shift 2 ;;
        --subnet-id)          SUBNET_ID="$2";          shift 2 ;;
        --stack-prefix)       STACK_PREFIX="$2";       shift 2 ;;
        --instance-type)      INSTANCE_TYPE="$2";      shift 2 ;;
        --allow-all-domains)  ALLOW_ALL_DOMAINS="true"; shift 1 ;;
        --allowed-domains)    ALLOWED_DOMAINS="$2";    shift 2 ;;
        --letsencrypt-email)  LETSENCRYPT_EMAIL="$2";  shift 2 ;;
        --bootstrap-peers)    BOOTSTRAP_PEERS="$2";    shift 2 ;;
        --ssh-cidr)           SSH_CIDR="$2";           shift 2 ;;
        --s3-bucket)          S3_BUCKET="$2";          shift 2 ;;
        --region)             REGION="$2";             shift 2 ;;
        -h|--help)            usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$REPO_ROOT/deploy/cloudformation.yaml"
DNS_STACK="${STACK_PREFIX}-dns"
NODE_STACK="${STACK_PREFIX}-node"

ok()      { echo "  [ok]    $*"; }
info()    { echo "  [info]  $*"; }
warn()    { echo "  [warn]  $*"; }
fail()    { echo "  [error] $*" >&2; exit 1; }
missing() { echo "" >&2; echo "Error: $* is required" >&2; echo "" >&2; usage >&2; exit 1; }

aws_cmd() {
    local args=(--profile "$PROFILE")
    [ -n "$REGION" ] && args+=(--region "$REGION")
    aws "${args[@]}" "$@"
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

echo "==> Checking prerequisites"
command -v aws >/dev/null 2>&1 || fail "aws CLI not found — https://aws.amazon.com/cli/"
ok "aws CLI: $(aws --version 2>&1 | head -1)"
command -v jq  >/dev/null 2>&1 || fail "jq not found — brew install jq / apt install jq"
ok "jq found"
[ -f "$TEMPLATE" ] || fail "Template not found: $TEMPLATE"
ok "Template: $TEMPLATE"

echo "==> Checking required parameters"
[ -z "$DOMAIN"    ] && missing "--domain"
[ -z "$PROFILE"   ] && missing "--profile"
[ -z "$KEY_NAME"  ] && missing "--key-name"
[ -z "$VPC_ID"    ] && missing "--vpc-id"
[ -z "$SUBNET_ID" ] && missing "--subnet-id"
[ "$ALLOW_ALL_DOMAINS" = "false" ] && [ -z "$ALLOWED_DOMAINS" ] && \
    { echo "" >&2; echo "Error: provide --allowed-domains DOMAINS or --allow-all-domains" >&2; echo "" >&2; usage >&2; exit 1; }
ok "Domain:        $DOMAIN"
ok "Key pair:      $KEY_NAME"
ok "VPC:           $VPC_ID"
ok "Subnet:        $SUBNET_ID"
ok "Instance type: $INSTANCE_TYPE"

echo "==> Checking AWS credentials"
IDENTITY=$(aws_cmd sts get-caller-identity 2>&1) \
    || fail "Profile '$PROFILE' is not authenticated: $IDENTITY"
ACCOUNT=$(echo "$IDENTITY" | jq -r '.Account')
ARN=$(echo "$IDENTITY" | jq -r '.Arn')
ok "Authenticated: $ARN (account $ACCOUNT)"

echo "==> Validating AWS resources"

# Key pair
aws_cmd ec2 describe-key-pairs --key-names "$KEY_NAME" \
    --query 'KeyPairs[0].KeyName' --output text >/dev/null 2>&1 \
    || fail "Key pair '$KEY_NAME' not found in this region/account"
ok "Key pair '$KEY_NAME' exists"

# VPC
VPC_STATE=$(aws_cmd ec2 describe-vpcs --vpc-ids "$VPC_ID" \
    --query 'Vpcs[0].State' --output text 2>&1) \
    || fail "VPC $VPC_ID not found"
[ "$VPC_STATE" = "available" ] || fail "VPC $VPC_ID is in state: $VPC_STATE"
ok "VPC $VPC_ID is available"

# Subnet — exists and belongs to the VPC
SUBNET_VPC=$(aws_cmd ec2 describe-subnets --subnet-ids "$SUBNET_ID" \
    --query 'Subnets[0].VpcId' --output text 2>&1) \
    || fail "Subnet $SUBNET_ID not found"
[ "$SUBNET_VPC" = "$VPC_ID" ] || \
    fail "Subnet $SUBNET_ID belongs to VPC $SUBNET_VPC, not $VPC_ID"
ok "Subnet $SUBNET_ID is in VPC $VPC_ID"

# Subnet — has a route to an internet gateway (public subnet)
IGW_ROUTE=$(aws_cmd ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
    --query "RouteTables[*].Routes[?GatewayId && starts_with(GatewayId,'igw-')] | [0][0].GatewayId" \
    --output text 2>/dev/null)
if [ "$IGW_ROUTE" = "None" ] || [ -z "$IGW_ROUTE" ]; then
    # Fallback: check the main route table for this VPC
    IGW_ROUTE=$(aws_cmd ec2 describe-route-tables \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=association.main,Values=true" \
        --query "RouteTables[*].Routes[?GatewayId && starts_with(GatewayId,'igw-')] | [0][0].GatewayId" \
        --output text 2>/dev/null)
fi
if [ "$IGW_ROUTE" = "None" ] || [ -z "$IGW_ROUTE" ]; then
    warn "Could not confirm $SUBNET_ID has an internet gateway route — Caddy/Let's Encrypt requires internet access"
else
    ok "Subnet has internet gateway route ($IGW_ROUTE)"
fi

# Existing S3 bucket (if provided)
if [ -n "$S3_BUCKET" ]; then
    aws_cmd s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null \
        || fail "S3 bucket '$S3_BUCKET' not found or not accessible"
    ok "S3 bucket '$S3_BUCKET' is accessible"
fi

echo "==> Checking DNS stack"
DNS_STATUS=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$DNS_STACK" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")
case "$DNS_STATUS" in
    CREATE_COMPLETE|UPDATE_COMPLETE)
        ok "DNS stack $DNS_STACK is $DNS_STATUS" ;;
    DOES_NOT_EXIST)
        fail "DNS stack $DNS_STACK not found. Run deploy-dns.sh first." ;;
    *IN_PROGRESS*)
        fail "DNS stack $DNS_STACK is $DNS_STATUS — wait for it to finish" ;;
    *)
        fail "DNS stack $DNS_STACK is in unexpected state: $DNS_STATUS" ;;
esac

ELASTIC_IP=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$DNS_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='ElasticIp'].OutputValue" \
    --output text)
ok "Elastic IP: $ELASTIC_IP"

echo "==> Checking node stack state"
NODE_STATUS=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$NODE_STACK" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

case "$NODE_STATUS" in
    DOES_NOT_EXIST)
        info "Stack $NODE_STACK does not exist — will create" ;;
    CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
        info "Stack $NODE_STACK is $NODE_STATUS — will update" ;;
    *IN_PROGRESS*)
        fail "Stack $NODE_STACK is $NODE_STATUS — wait for it to finish first" ;;
    *FAILED*|ROLLBACK_COMPLETE)
        fail "Stack $NODE_STACK is in $NODE_STATUS. Run stop-node.sh to clean up first." ;;
    *)
        warn "Stack $NODE_STACK status: $NODE_STATUS — proceeding" ;;
esac

# ---------------------------------------------------------------------------
# Build parameter overrides
# ---------------------------------------------------------------------------

PARAMS=(
    "DnsStackName=${DNS_STACK}"
    "DomainName=${DOMAIN}"
    "InstanceType=${INSTANCE_TYPE}"
    "KeyName=${KEY_NAME}"
    "VpcId=${VPC_ID}"
    "SubnetId=${SUBNET_ID}"
    "AllowAllDomains=${ALLOW_ALL_DOMAINS}"
    "SshAccessCidr=${SSH_CIDR}"
)
[ -n "$ALLOWED_DOMAINS"    ] && PARAMS+=("AllowedDomains=${ALLOWED_DOMAINS}")
[ -n "$LETSENCRYPT_EMAIL"  ] && PARAMS+=("LetsEncryptEmail=${LETSENCRYPT_EMAIL}")
[ -n "$BOOTSTRAP_PEERS"    ] && PARAMS+=("BootstrapPeers=${BOOTSTRAP_PEERS}")
[ -n "$S3_BUCKET"          ] && PARAMS+=("S3BucketName=${S3_BUCKET}")

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

echo ""
echo "==> Deploying $NODE_STACK"
aws_cmd cloudformation deploy \
    --stack-name "$NODE_STACK" \
    --template-file "$TEMPLATE" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "${PARAMS[@]}" \
    --no-fail-on-empty-changeset

echo ""
echo "==> Stack outputs"
aws_cmd cloudformation describe-stacks \
    --stack-name "$NODE_STACK" \
    --query 'Stacks[0].Outputs[*].{Key:OutputKey,Value:OutputValue}' \
    --output table

echo ""
echo "Node is starting. Once DNS has propagated, Caddy will obtain the TLS certificate."
echo "Watch progress with:"
echo "  ./scripts/node-status.sh --domain $DOMAIN --profile $PROFILE"
