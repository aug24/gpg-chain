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
Usage: $(basename "$0") --domain DOMAIN --profile PROFILE --region REGION [options]

Required:
  --domain DOMAIN           FQDN matching the DNS stack (e.g. keys.example.com)
  --profile PROFILE         AWS CLI profile name
  --region REGION           AWS region (e.g. eu-west-2)

Optional:
  --stack-prefix PREFIX     Stack name prefix (default: gpgchain)
  --instance-type TYPE      EC2 instance type (default: t3.small)
  --allow-all-domains       Accept keys from any email domain
  --allowed-domains DOMAINS Comma-separated allowed email domains
  --letsencrypt-email EMAIL  Email for Let's Encrypt notifications
  --bootstrap-peers PEERS   Comma-separated peer node URLs
  --s3-bucket BUCKET        Existing S3 bucket name (default: auto-create)
  -h, --help

Shell access to the instance is via AWS SSM Session Manager — no key pair or open SSH port required.
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

DOMAIN="" PROFILE=""
STACK_PREFIX="gpgchain" INSTANCE_TYPE="t3.small"
ALLOW_ALL_DOMAINS="false" ALLOWED_DOMAINS="" LETSENCRYPT_EMAIL=""
BOOTSTRAP_PEERS="" S3_BUCKET="" REGION=""

[[ $# -eq 0 ]] && { usage; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)             DOMAIN="$2";             shift 2 ;;
        --profile)            PROFILE="$2";            shift 2 ;;
        --stack-prefix)       STACK_PREFIX="$2";       shift 2 ;;
        --instance-type)      INSTANCE_TYPE="$2";      shift 2 ;;
        --allow-all-domains)  ALLOW_ALL_DOMAINS="true"; shift 1 ;;
        --allowed-domains)    ALLOWED_DOMAINS="$2";    shift 2 ;;
        --letsencrypt-email)  LETSENCRYPT_EMAIL="$2";  shift 2 ;;
        --bootstrap-peers)    BOOTSTRAP_PEERS="$2";    shift 2 ;;
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

trap 'echo "" >&2; echo "  [error] Script failed on line $LINENO — see output above for details." >&2' ERR

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
[ -z "$DOMAIN"  ] && missing "--domain"
[ -z "$PROFILE" ] && missing "--profile"
[ "$ALLOW_ALL_DOMAINS" = "false" ] && [ -z "$ALLOWED_DOMAINS" ] && \
    { echo "" >&2; echo "Error: provide --allowed-domains DOMAINS or --allow-all-domains" >&2; echo "" >&2; usage >&2; exit 1; }
ok "Domain:        $DOMAIN"
ok "Instance type: $INSTANCE_TYPE"

echo "==> Checking AWS credentials"
IDENTITY=$(aws_cmd sts get-caller-identity 2>&1) \
    || fail "Profile '$PROFILE' is not authenticated: $IDENTITY"
ACCOUNT=$(echo "$IDENTITY" | jq -r '.Account')
ARN=$(echo "$IDENTITY" | jq -r '.Arn')
ok "Authenticated: $ARN (account $ACCOUNT)"

[ -z "$REGION" ] && missing "--region"
ok "Region: $REGION"

echo "==> Looking up latest Amazon Linux 2023 AMI"
AMI_ID=$(aws_cmd ssm get-parameter \
    --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" \
    --query "Parameter.Value" \
    --output text) \
    || fail "Could not look up AL2023 AMI in $REGION"
ok "AMI: $AMI_ID"

echo "==> Detecting default VPC and subnet"
VPC_ID=$(aws_cmd ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --query "Vpcs[0].VpcId" \
    --output text) \
    || fail "Could not query EC2 in $REGION — check credentials and region"
if [ -z "$VPC_ID" ] || [ "$VPC_ID" = "None" ]; then
    fail "No default VPC found in $REGION"
fi
ok "Default VPC: $VPC_ID"

SUBNET_ID=$(aws_cmd ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=defaultForAz,Values=true" \
    --query "Subnets[0].SubnetId" \
    --output text) \
    || fail "Could not query subnets in VPC $VPC_ID"
if [ -z "$SUBNET_ID" ] || [ "$SUBNET_ID" = "None" ]; then
    fail "No default subnet found in VPC $VPC_ID"
fi
ok "Subnet: $SUBNET_ID"

echo "==> Validating AWS resources"

# Use existing bucket if one was left from a previous deployment
DEFAULT_BUCKET="${NODE_STACK}-gpgchain-data"
if [ -z "$S3_BUCKET" ]; then
    if aws_cmd s3api head-bucket --bucket "$DEFAULT_BUCKET" 2>/dev/null; then
        S3_BUCKET="$DEFAULT_BUCKET"
        ok "Reusing existing S3 bucket: $S3_BUCKET"
    fi
else
    aws_cmd s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null \
        || fail "S3 bucket '$S3_BUCKET' not found or not accessible"
    ok "S3 bucket '$S3_BUCKET' is accessible"
fi

echo "==> Checking DNS stack"
DNS_RAW=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$DNS_STACK" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>&1)
DNS_EXIT=$?
if [ $DNS_EXIT -ne 0 ]; then
    if echo "$DNS_RAW" | grep -qi "does not exist\|stack.*not found"; then
        fail "DNS stack '$DNS_STACK' not found. Run: ./scripts/deploy-dns.sh --domain $DOMAIN --profile $PROFILE"
    else
        fail "Error checking DNS stack '$DNS_STACK': $DNS_RAW"
    fi
fi
DNS_STATUS="$DNS_RAW"
case "$DNS_STATUS" in
    CREATE_COMPLETE|UPDATE_COMPLETE)
        ok "DNS stack $DNS_STACK is $DNS_STATUS" ;;
    *IN_PROGRESS*)
        fail "DNS stack $DNS_STACK is $DNS_STATUS — wait for it to finish" ;;
    *)
        fail "DNS stack $DNS_STACK is in unexpected state: $DNS_STATUS" ;;
esac

ELASTIC_IP=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$DNS_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='ElasticIp'].OutputValue" \
    --output text)
ELASTIC_IP_ALLOC=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$DNS_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='ElasticIpAllocationId'].OutputValue" \
    --output text)
ok "Elastic IP: $ELASTIC_IP (alloc $ELASTIC_IP_ALLOC)"

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
    REVIEW_IN_PROGRESS|*FAILED*|ROLLBACK_COMPLETE)
        fail "Stack $NODE_STACK is in $NODE_STATUS. Run stop-node.sh to clean up first." ;;
    *IN_PROGRESS*)
        fail "Stack $NODE_STACK is $NODE_STATUS — wait for it to finish first" ;;
    *)
        warn "Stack $NODE_STACK status: $NODE_STATUS — proceeding" ;;
esac

# ---------------------------------------------------------------------------
# Build parameter overrides
# ---------------------------------------------------------------------------

PARAMS=(
    "AmiId=${AMI_ID}"
    "DomainName=${DOMAIN}"
    "VpcId=${VPC_ID}"
    "SubnetId=${SUBNET_ID}"
    "InstanceType=${INSTANCE_TYPE}"
    "AllowAllDomains=${ALLOW_ALL_DOMAINS}"
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
echo "==> Associating Elastic IP"
INSTANCE_ID=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$NODE_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
    --output text)
aws_cmd ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ELASTIC_IP_ALLOC" \
    --allow-reassociation >/dev/null
ok "Elastic IP $ELASTIC_IP associated with $INSTANCE_ID"

echo ""
echo "Node is starting. Once DNS has propagated, Caddy will obtain the TLS certificate."
echo "Watch progress with:"
echo "  ./scripts/node-status.sh --domain $DOMAIN --profile $PROFILE --region $REGION"
