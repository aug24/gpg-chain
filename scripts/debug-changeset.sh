#!/usr/bin/env bash
# Show the latest changeset for a GPG Chain stack — useful for diagnosing
# failed changeset creation errors.
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") --profile PROFILE --region REGION [options]

Required:
  --profile PROFILE    AWS CLI profile name
  --region REGION      AWS region (e.g. eu-west-2)

Optional:
  --stack-prefix PREFIX  Stack name prefix (default: gpgchain)
  --stack (dns|node)     Which stack to inspect (default: node)
  -h, --help
EOF
}

PROFILE="" REGION="" STACK_PREFIX="gpgchain" WHICH="node"

[[ $# -eq 0 ]] && { usage; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)      PROFILE="$2";      shift 2 ;;
        --region)       REGION="$2";       shift 2 ;;
        --stack-prefix) STACK_PREFIX="$2"; shift 2 ;;
        --stack)        WHICH="$2";        shift 2 ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

[ -z "$PROFILE" ] && { echo "Error: --profile is required" >&2; usage >&2; exit 1; }
[ -z "$REGION"  ] && { echo "Error: --region is required"  >&2; usage >&2; exit 1; }

STACK_NAME="${STACK_PREFIX}-${WHICH}"

aws_cmd() {
    aws --profile "$PROFILE" --region "$REGION" "$@"
}

# Stack state
echo "==> Stack: $STACK_NAME"
STACK_STATUS=$(aws_cmd cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")
echo "  Status: $STACK_STATUS"

# Latest changeset
echo ""
echo "==> Latest changeset"
CHANGESET_NAME=$(aws_cmd cloudformation list-change-sets \
    --stack-name "$STACK_NAME" \
    --query 'sort_by(Summaries, &CreationTime)[-1].ChangeSetName' \
    --output text 2>/dev/null || echo "")

if [ -z "$CHANGESET_NAME" ] || [ "$CHANGESET_NAME" = "None" ]; then
    echo "  No changesets found."
    exit 0
fi

echo "  Name:   $CHANGESET_NAME"

STATUS=$(aws_cmd cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGESET_NAME" \
    --query 'Status' --output text)
EXEC_STATUS=$(aws_cmd cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGESET_NAME" \
    --query 'ExecutionStatus' --output text)
REASON=$(aws_cmd cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGESET_NAME" \
    --query 'StatusReason' --output text)

echo "  Status: $STATUS / $EXEC_STATUS"
[ -n "$REASON" ] && [ "$REASON" != "None" ] && echo "  Reason: $REASON"

echo ""
echo "==> Parameters used"
aws_cmd cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGESET_NAME" \
    --query 'Parameters[*].[ParameterKey,ParameterValue]' \
    --output table

echo ""
echo "==> Planned changes"
aws_cmd cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGESET_NAME" \
    --query 'Changes[*].ResourceChange.[Action,LogicalResourceId,ResourceType]' \
    --output table

echo ""
echo "==> All stack events (most recent first)"
aws_cmd cloudformation describe-stack-events \
    --stack-name "$STACK_NAME" \
    --query 'StackEvents[*].[Timestamp,ResourceType,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
    --output table 2>/dev/null || echo "  (no events)"

echo ""
echo "==> Template validation"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../deploy/cloudformation.yaml"
aws_cmd cloudformation validate-template \
    --template-body "file://$TEMPLATE" \
    && echo "  Template is valid." \
    || echo "  Template validation FAILED (see above)."
