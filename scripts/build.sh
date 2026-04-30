#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building Go implementation"
cd "$ROOT/implementations/go"
go build ./...
echo "    go build OK"

echo "==> Installing Python implementation"
cd "$ROOT/implementations/python"
pip3 install -e . --quiet
echo "    pip install OK"

echo "==> Installing test dependencies"
cd "$ROOT/tests"
pip3 install -r requirements.txt --quiet
echo "    test deps OK"

echo "==> Build complete"
