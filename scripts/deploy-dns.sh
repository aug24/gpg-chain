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
Usage: $(basename "$0") --domain DOMAIN --profile PROFILE [options]

Required:
  --domain DOMAIN           FQDN for this node (e.g. keys.example.com)
  --profile PROFILE         AWS CLI profile name

Optional:
  --hosted-zone-id ZONE_ID  Route 53 Hosted Zone ID — looked up automatically if omitted
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

[[ $# -eq 0 ]] && { usage; exit 1; }

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

ok()      { echo "  [ok]    $*"; }
info()    { echo "  [info]  $*"; }
warn()    { echo "  [warn]  $*"; }
fail()    { echo "  [error] $*" >&2; exit 1; }
missing() { echo "" >&2; echo "Error: $* is required" >&2; echo "" >&2; usage >&2; exit 1; }

# Walk up the domain hierarchy looking for a Route 53 hosted zone.
# e.g. keys.example.com → try example.com → try com
lookup_hosted_zone() {
    local domain="$1"
    local candidate="${domain#*.}"   # strip first label to start one level up
    while [[ "$candidate" == *.* ]]; do
        local zone_id
        zone_id=$(aws_cmd route53 list-hosted-zones-by-name \
            --dns-name "${candidate}." \
            --query "HostedZones[?Name=='${candidate}.'].Id | [0]" \
            --output text 2>/dev/null)
        if [ -n "$zone_id" ] && [ "$zone_id" != "None" ]; then
            echo "${zone_id##*/}"   # strip /hostedzone/ prefix
            return 0
        fi
        candidate="${candidate#*.}"
    done
    return 1
}

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
ok "Domain:  $DOMAIN"
ok "Profile: $PROFILE"

echo "==> Checking AWS credentials"
IDENTITY=$(aws_cmd sts get-caller-identity 2>&1) \
    || fail "Profile '$PROFILE' is not authenticated: $IDENTITY"
ACCOUNT=$(echo "$IDENTITY" | jq -r '.Account')
ARN=$(echo "$IDENTITY" | jq -r '.Arn')
ok "Authenticated: $ARN (account $ACCOUNT)"

echo "==> Resolving hosted zone"
if [ -z "$HOSTED_ZONE_ID" ]; then
    info "No --hosted-zone-id supplied — looking up from domain hierarchy..."
    HOSTED_ZONE_ID=$(lookup_hosted_zone "$DOMAIN") \
        || fail "Could not find a Route 53 hosted zone for any parent of '$DOMAIN'. Pass --hosted-zone-id explicitly."
    ok "Found hosted zone: $HOSTED_ZONE_ID"
fi
ZONE=$(aws_cmd route53 get-hosted-zone --id "$HOSTED_ZONE_ID" 2>&1) \
    || fail "Hosted zone $HOSTED_ZONE_ID not found or not accessible"
ZONE_NAME=$(echo "$ZONE" | jq -r '.HostedZone.Name')
ok "Hosted zone $HOSTED_ZONE_ID ($ZONE_NAME)"

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
