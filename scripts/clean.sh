#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Stopping cluster"
"$ROOT/scripts/cluster.sh" stop 2>/dev/null || true

echo "==> Removing data directories"
rm -rf "$ROOT/data"

echo "==> Clean complete"
