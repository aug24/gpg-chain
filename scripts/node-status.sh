#!/usr/bin/env bash
# Show the current status of the GPG Chain DNS and node stacks,
# and check whether the node is responding.
set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") --domain DOMAIN --profile PROFILE [options]

Required:
  --domain DOMAIN    FQDN of the node (e.g. demo.gpgchain.co.uk)
  --profile PROFILE  AWS CLI profile name

Optional:
  --stack-prefix PREFIX  Stack name prefix (default: gpgchain)
  --region REGION        AWS region (default: profile default)
  -h, --help
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

DOMAIN="" PROFILE="" STACK_PREFIX="gpgchain" REGION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)       DOMAIN="$2";       shift 2 ;;
        --profile)      PROFILE="$2";      shift 2 ;;
        --stack-prefix) STACK_PREFIX="$2"; shift 2 ;;
        --region)       REGION="$2";       shift 2 ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DNS_STACK="${STACK_PREFIX}-dns"
NODE_STACK="${STACK_PREFIX}-node"

ok()   { echo "  [ok]      $*"; }
info() { echo "  [info]    $*"; }
warn() { echo "  [warn]    $*"; }
fail() { echo "  [error]   $*" >&2; exit 1; }
row()  { printf "  %-18s %s\n" "$1" "$2"; }

aws_cmd() {
    local args=(--profile "$PROFILE")
    [ -n "$REGION" ] && args+=(--region "$REGION")
    aws "${args[@]}" "$@"
}

stack_status() {
    aws_cmd cloudformation describe-stacks \
        --stack-name "$1" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT DEPLOYED"
}

stack_output() {
    aws_cmd cloudformation describe-stacks \
        --stack-name "$1" \
        --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

[ -z "$DOMAIN"  ] && { usage; exit 1; }
[ -z "$PROFILE" ] && { usage; exit 1; }

command -v aws  >/dev/null 2>&1 || fail "aws CLI not found"
command -v jq   >/dev/null 2>&1 || fail "jq not found"
command -v curl >/dev/null 2>&1 || fail "curl not found"

IDENTITY=$(aws_cmd sts get-caller-identity 2>&1) \
    || fail "Profile '$PROFILE' is not authenticated"

# ---------------------------------------------------------------------------
# DNS stack
# ---------------------------------------------------------------------------

echo ""
echo "==> DNS stack: $DNS_STACK"
DNS_STATUS=$(stack_status "$DNS_STACK")
row "Status:" "$DNS_STATUS"

case "$DNS_STATUS" in
    CREATE_COMPLETE|UPDATE_COMPLETE)
        ELASTIC_IP=$(stack_output "$DNS_STACK" "ElasticIp")
        row "Elastic IP:" "$ELASTIC_IP"

        # Check what the domain resolves to
        if command -v dig >/dev/null 2>&1; then
            RESOLVED=$(dig +short "$DOMAIN" A 2>/dev/null | head -1)
        elif command -v nslookup >/dev/null 2>&1; then
            RESOLVED=$(nslookup "$DOMAIN" 2>/dev/null | awk '/^Address: /{print $2}' | tail -1)
        else
            RESOLVED=""
        fi

        if [ -z "$RESOLVED" ]; then
            warn "DNS: $DOMAIN does not resolve yet"
        elif [ "$RESOLVED" = "$ELASTIC_IP" ]; then
            ok "DNS: $DOMAIN → $RESOLVED (correct)"
        else
            warn "DNS: $DOMAIN → $RESOLVED (expected $ELASTIC_IP — propagation may be in progress)"
        fi
        ;;
    NOT\ DEPLOYED)
        warn "DNS stack not deployed. Run: ./scripts/deploy-dns.sh --domain $DOMAIN --profile $PROFILE ..." ;;
    *IN_PROGRESS*)
        info "DNS stack operation in progress..." ;;
    *)
        warn "DNS stack status: $DNS_STATUS" ;;
esac

# ---------------------------------------------------------------------------
# Node stack
# ---------------------------------------------------------------------------

echo ""
echo "==> Node stack: $NODE_STACK"
NODE_STATUS=$(stack_status "$NODE_STACK")
row "Status:" "$NODE_STATUS"

case "$NODE_STATUS" in
    CREATE_COMPLETE|UPDATE_COMPLETE)
        INSTANCE_ID=$(stack_output "$NODE_STACK" "InstanceId")
        row "Instance:" "$INSTANCE_ID"

        # Instance state
        INSTANCE_STATE=$(aws_cmd ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text 2>/dev/null || echo "unknown")
        row "Instance state:" "$INSTANCE_STATE"

        # Uptime (launch time)
        LAUNCH_TIME=$(aws_cmd ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --query 'Reservations[0].Instances[0].LaunchTime' \
            --output text 2>/dev/null || echo "")
        [ -n "$LAUNCH_TIME" ] && row "Running since:" "$LAUNCH_TIME"
        ;;
    NOT\ DEPLOYED)
        info "Node stack not deployed (DNS and S3 data are intact)"
        echo ""
        echo "  Start the node with:"
        echo "    ./scripts/deploy-node.sh --domain $DOMAIN --profile $PROFILE \\"
        echo "      --key-name <KEY> --vpc-id <VPC> --subnet-id <SUBNET>"
        ;;
    DELETE_IN_PROGRESS)
        info "Node stack is being deleted..." ;;
    *IN_PROGRESS*)
        info "Node stack operation in progress..." ;;
    *FAILED*)
        warn "Node stack is in $NODE_STATUS"
        echo "  Check events with:"
        echo "    aws cloudformation describe-stack-events --stack-name $NODE_STACK --profile $PROFILE" ;;
esac

# ---------------------------------------------------------------------------
# HTTPS endpoint check
# ---------------------------------------------------------------------------

echo ""
echo "==> Node endpoint: https://$DOMAIN"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout 5 --max-time 10 \
    "https://$DOMAIN/.well-known/gpgchain.json" 2>/dev/null || echo "unreachable")

case "$HTTP_STATUS" in
    200)
        ok "HTTPS: responding (200 OK)"
        WELL_KNOWN=$(curl -s --connect-timeout 5 --max-time 10 \
            "https://$DOMAIN/.well-known/gpgchain.json" 2>/dev/null)
        if [ -n "$WELL_KNOWN" ]; then
            NODE_URL=$(echo "$WELL_KNOWN"  | jq -r '.node_url  // "not set"' 2>/dev/null)
            DOMAINS=$(echo  "$WELL_KNOWN"  | jq -r '.domains   | join(", ") // "none"' 2>/dev/null)
            ALLOW_ALL=$(echo "$WELL_KNOWN" | jq -r '.allow_all // false' 2>/dev/null)
            row "node_url:"   "$NODE_URL"
            row "domains:"    "$DOMAINS"
            row "allow_all:"  "$ALLOW_ALL"
        fi
        ;;
    000|unreachable)
        warn "HTTPS: not reachable (node may still be starting or DNS not yet propagated)" ;;
    301|302)
        warn "HTTPS: redirect ($HTTP_STATUS) — Caddy may still be obtaining certificate" ;;
    *)
        warn "HTTPS: unexpected status $HTTP_STATUS" ;;
esac

echo ""
