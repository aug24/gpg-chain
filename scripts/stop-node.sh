#!/usr/bin/env bash
# Delete the GPG Chain node stack (turn off the expensive bit).
# The DNS stack, Elastic IP, and S3 data are all preserved.
# Redeploy at any time with deploy-node.sh.
set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") --domain DOMAIN --profile PROFILE [options]

Deletes the node stack. The DNS stack, Elastic IP, and S3 block store
are retained — redeploy at any time with deploy-node.sh.

Required:
  --domain DOMAIN    FQDN matching the node stack (e.g. demo.gpgchain.co.uk)
  --profile PROFILE  AWS CLI profile name

Optional:
  --stack-prefix PREFIX  Stack name prefix (default: gpgchain)
  --region REGION        AWS region (default: profile default)
  --yes                  Skip confirmation prompt
  -h, --help
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

DOMAIN="" PROFILE="" STACK_PREFIX="gpgchain" REGION="" YES=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)       DOMAIN="$2";       shift 2 ;;
        --profile)      PROFILE="$2";      shift 2 ;;
        --stack-prefix) STACK_PREFIX="$2"; shift 2 ;;
        --region)       REGION="$2";       shift 2 ;;
        --yes)          YES=true;          shift 1 ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NODE_STACK="${STACK_PREFIX}-node"

ok()   { echo "  [ok]    $*"; }
info() { echo "  [info]  $*"; }
fail() { echo "  [error] $*" >&2; exit 1; }

aws_cmd() {
    local args=(--profile "$PROFILE")
    [ -n "$REGION" ] && args+=(--region "$REGION")
    aws "${args[@]}" "$@"
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

echo "==> Checking prerequisites"
command -v aws >/dev/null 2>&1 || fail "aws CLI not found"
command -v jq  >/dev/null 2>&1 || fail "jq not found"
ok "aws CLI and jq found"

echo "==> Checking required parameters"
[ -z "$DOMAIN"  ] && fail "--domain is required"
[ -z "$PROFILE" ] && fail "--profile is required"
ok "Domain:  $DOMAIN"
ok "Profile: $PROFILE"

echo "==> Checking AWS credentials"
IDENTITY=$(aws_cmd sts get-caller-identity 2>&1) \
    || fail "Profile '$PROFILE' is not authenticated: $IDENTITY"
ok "Authenticated: $(echo "$IDENTITY" | jq -r '.Arn') (account $(echo "$IDENTITY" | jq -r '.Account'))"

echo "==> Checking node stack"
NODE_STATUS=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$NODE_STACK" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

case "$NODE_STATUS" in
    DOES_NOT_EXIST)
        info "Stack $NODE_STACK does not exist — nothing to do"
        exit 0 ;;
    CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
        ok "Stack $NODE_STACK is $NODE_STATUS" ;;
    DELETE_IN_PROGRESS)
        fail "Stack $NODE_STACK is already being deleted" ;;
    *IN_PROGRESS*)
        fail "Stack $NODE_STACK is $NODE_STATUS — wait for it to finish first" ;;
    *)
        ok "Stack $NODE_STACK is $NODE_STATUS" ;;
esac

# Show what will be retained
echo ""
echo "  The following will be RETAINED:"
BUCKET=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$NODE_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
    --output text 2>/dev/null || echo "(unknown)")
DNS_STACK="${STACK_PREFIX}-dns"
ELASTIC_IP=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$DNS_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='ElasticIp'].OutputValue" \
    --output text 2>/dev/null || echo "(check DNS stack)")
info "S3 bucket:  $BUCKET (block store data preserved)"
info "Elastic IP: $ELASTIC_IP (DNS record unchanged)"
info "DNS stack:  $DNS_STACK (untouched)"
echo ""

# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------

if [ "$YES" != true ]; then
    read -r -p "Delete node stack '$NODE_STACK'? [y/N] " CONFIRM
    [[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

echo ""
echo "==> Deleting $NODE_STACK"
aws_cmd cloudformation delete-stack --stack-name "$NODE_STACK"

echo "Waiting for deletion to complete..."
aws_cmd cloudformation wait stack-delete-complete --stack-name "$NODE_STACK"

echo ""
echo "Node stack deleted. Your data in S3 and your DNS record are intact."
echo "Bring it back up with:"
echo "  ./scripts/deploy-node.sh --domain $DOMAIN --profile $PROFILE ..."
