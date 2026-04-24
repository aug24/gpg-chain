#!/usr/bin/env bash
# Deploy the permanent DNS layer: Elastic IP + Route 53 A record.
# Run once and leave running. Delete the node stack when not in use;
# this stack (and your data in S3) persists between deployments.
set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") --domain DOMAIN --hosted-zone-id ZONE_ID --profile PROFILE [options]

Required:
  --domain DOMAIN           FQDN for this node (e.g. demo.gpgchain.co.uk)
  --hosted-zone-id ZONE_ID  Route 53 Hosted Zone ID (e.g. Z1PA6795UKMFR9)
  --profile PROFILE         AWS CLI profile name

Optional:
  --stack-prefix PREFIX     Stack name prefix (default: gpgchain)
  --ttl TTL                 DNS TTL in seconds (default: 300)
  --region REGION           AWS region (default: profile default)
  -h, --help
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

DOMAIN="" HOSTED_ZONE_ID="" PROFILE=""
STACK_PREFIX="gpgchain" TTL="300" REGION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)         DOMAIN="$2";         shift 2 ;;
        --hosted-zone-id) HOSTED_ZONE_ID="$2"; shift 2 ;;
        --profile)        PROFILE="$2";        shift 2 ;;
        --stack-prefix)   STACK_PREFIX="$2";   shift 2 ;;
        --ttl)            TTL="$2";            shift 2 ;;
        --region)         REGION="$2";         shift 2 ;;
        -h|--help)        usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$REPO_ROOT/deploy/dns.yaml"
STACK_NAME="${STACK_PREFIX}-dns"

ok()   { echo "  [ok]    $*"; }
info() { echo "  [info]  $*"; }
warn() { echo "  [warn]  $*"; }
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
command -v aws >/dev/null 2>&1 || fail "aws CLI not found — https://aws.amazon.com/cli/"
ok "aws CLI: $(aws --version 2>&1 | head -1)"
command -v jq  >/dev/null 2>&1 || fail "jq not found — brew install jq / apt install jq"
ok "jq found"
[ -f "$TEMPLATE" ] || fail "Template not found: $TEMPLATE"
ok "Template: $TEMPLATE"

echo "==> Checking required parameters"
[ -z "$DOMAIN"         ] && fail "--domain is required"
[ -z "$HOSTED_ZONE_ID" ] && fail "--hosted-zone-id is required"
[ -z "$PROFILE"        ] && fail "--profile is required"
ok "Domain:         $DOMAIN"
ok "Hosted zone ID: $HOSTED_ZONE_ID"
ok "Profile:        $PROFILE"

echo "==> Checking AWS credentials"
IDENTITY=$(aws_cmd sts get-caller-identity 2>&1) \
    || fail "Profile '$PROFILE' is not authenticated: $IDENTITY"
ACCOUNT=$(echo "$IDENTITY" | jq -r '.Account')
ARN=$(echo "$IDENTITY" | jq -r '.Arn')
ok "Authenticated: $ARN (account $ACCOUNT)"

echo "==> Validating AWS resources"
ZONE=$(aws_cmd route53 get-hosted-zone --id "$HOSTED_ZONE_ID" 2>&1) \
    || fail "Hosted zone $HOSTED_ZONE_ID not found or not accessible"
ZONE_NAME=$(echo "$ZONE" | jq -r '.HostedZone.Name')
ok "Hosted zone $HOSTED_ZONE_ID found ($ZONE_NAME)"

EXISTING=$(aws_cmd route53 list-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --query "ResourceRecordSets[?Name=='${DOMAIN}.' && Type=='A'] | [0].ResourceRecords[0].Value" \
    --output text 2>/dev/null)
if [ "$EXISTING" != "None" ] && [ -n "$EXISTING" ]; then
    warn "Existing A record for $DOMAIN points to $EXISTING — will be overwritten"
else
    ok "No existing A record for $DOMAIN"
fi

echo "==> Checking stack state"
STACK_STATUS=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

case "$STACK_STATUS" in
    DOES_NOT_EXIST)
        info "Stack $STACK_NAME does not exist — will create" ;;
    CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
        info "Stack $STACK_NAME is $STACK_STATUS — will update" ;;
    *IN_PROGRESS*)
        fail "Stack $STACK_NAME is $STACK_STATUS — wait for it to finish first" ;;
    *FAILED*|ROLLBACK_COMPLETE)
        fail "Stack $STACK_NAME is in $STACK_STATUS. Delete it manually then retry." ;;
    *)
        warn "Stack $STACK_NAME status: $STACK_STATUS — proceeding" ;;
esac

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

echo ""
echo "==> Deploying $STACK_NAME"
aws_cmd cloudformation deploy \
    --stack-name "$STACK_NAME" \
    --template-file "$TEMPLATE" \
    --parameter-overrides \
        DomainName="$DOMAIN" \
        HostedZoneId="$HOSTED_ZONE_ID" \
        TTL="$TTL" \
    --no-fail-on-empty-changeset

echo ""
echo "==> Stack outputs"
aws_cmd cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[*].{Key:OutputKey,Value:OutputValue}' \
    --output table

echo ""
echo "DNS stack is live. Deploy the node with:"
echo "  ./scripts/deploy-node.sh --domain $DOMAIN --profile $PROFILE \\"
echo "    --key-name <KEY> --vpc-id <VPC> --subnet-id <SUBNET>"
