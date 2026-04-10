#!/usr/bin/env bash
# Run the full behave test suite against a live Docker Compose cluster.
# Usage:
#   ./scripts/integration-test.sh          # build, test, tear down
#   ./scripts/integration-test.sh --no-build   # skip rebuild (faster on re-runs)
#   ./scripts/integration-test.sh --keep-up    # leave cluster running after tests

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD=1
KEEP_UP=0

for arg in "$@"; do
  case "$arg" in
    --no-build)  BUILD=0 ;;
    --keep-up)   KEEP_UP=1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

cleanup() {
  if [[ $KEEP_UP -eq 0 ]]; then
    echo "--- Stopping cluster ---"
    docker compose down -v --remove-orphans 2>/dev/null || true
  else
    echo "--- Cluster left running (--keep-up) ---"
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local max=30
  local i=0
  echo -n "Waiting for $label "
  while ! curl -sf "$url" >/dev/null 2>&1; do
    i=$((i+1))
    if [[ $i -ge $max ]]; then
      echo " TIMEOUT"
      echo "ERROR: $label did not become ready at $url"
      return 1
    fi
    echo -n "."
    sleep 1
  done
  echo " ready"
}

# ---------------------------------------------------------------------------
# Build & start
# ---------------------------------------------------------------------------

trap cleanup EXIT

if [[ $BUILD -eq 1 ]]; then
  echo "--- Building images ---"
  docker compose build
fi

echo "--- Starting cluster ---"
docker compose up -d

wait_for_url "http://localhost:8080/peers" "node-a"
wait_for_url "http://localhost:8081/peers" "node-b"
wait_for_url "http://localhost:8082/peers" "node-c"

echo "--- All nodes ready ---"

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

# Install test dependencies if needed
if ! python -c "import behave" 2>/dev/null; then
  pip install -q behave requests pgpy
fi
if ! python -c "import gpgchain" 2>/dev/null; then
  pip install -q -e implementations/python/
fi

echo "--- Running behave against cluster ---"
GPGCHAIN_TEST_SERVER="http://localhost:8080,http://localhost:8081,http://localhost:8082" \
  behave tests/ --no-capture "$@" || {
    echo "--- TESTS FAILED ---"
    exit 1
  }

echo "--- All tests passed ---"
