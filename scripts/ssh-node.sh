#!/usr/bin/env bash
# Open an SSM Session Manager shell on the GPG Chain node.
# Requires the AWS Session Manager plugin: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") --profile PROFILE --region REGION [options]

Required:
  --profile PROFILE    AWS CLI profile name
  --region REGION      AWS region (e.g. eu-west-1)

Optional:
  --stack-prefix PREFIX  Stack name prefix (default: gpgchain)
  --log                  Tail the setup log instead of opening a shell
  -h, --help
EOF
}

PROFILE="" REGION="" STACK_PREFIX="gpgchain" LOG=false

[[ $# -eq 0 ]] && { usage; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)      PROFILE="$2";      shift 2 ;;
        --region)       REGION="$2";       shift 2 ;;
        --stack-prefix) STACK_PREFIX="$2"; shift 2 ;;
        --log)          LOG=true;          shift 1 ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

[ -z "$PROFILE" ] && { echo "Error: --profile is required" >&2; usage >&2; exit 1; }
[ -z "$REGION"  ] && { echo "Error: --region is required"  >&2; usage >&2; exit 1; }

NODE_STACK="${STACK_PREFIX}-node"

INSTANCE_ID=$(aws --profile "$PROFILE" --region "$REGION" cloudformation describe-stacks \
    --stack-name "$NODE_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
    --output text 2>/dev/null)

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "  [error] Could not find instance ID — is the node stack deployed?" >&2
    exit 1
fi

echo "  [ok]  Instance: $INSTANCE_ID"

if [ "$LOG" = true ]; then
    echo "  [info] Tailing setup log (Ctrl-C to exit)..."
    aws --profile "$PROFILE" --region "$REGION" ssm start-session \
        --target "$INSTANCE_ID" \
        --document-name AWS-StartInteractiveCommand \
        --parameters '{"command":["sudo tail -f /var/log/gpgchain-setup.log"]}'
else
    echo "  [info] Opening shell (type 'exit' to close)..."
    aws --profile "$PROFILE" --region "$REGION" ssm start-session \
        --target "$INSTANCE_ID"
fi
