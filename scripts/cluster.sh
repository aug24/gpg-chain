#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_DIR="$ROOT/.cluster"
DATA_DIR="$ROOT/data"
BASE_PORT=8080

usage() {
  echo "usage: cluster.sh <start|stop|status>"
  echo "  start --go N --python M   start N Go nodes and M Python nodes"
  echo "  stop                      stop all running nodes"
  echo "  status                    show running nodes"
  exit 1
}

cmd="${1:-}"
shift || true

case "$cmd" in
  start)
    GO_COUNT=0
    PYTHON_COUNT=0
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --go)     GO_COUNT="$2";     shift 2 ;;
        --python) PYTHON_COUNT="$2"; shift 2 ;;
        *) echo "unknown flag: $1"; usage ;;
      esac
    done

    mkdir -p "$CLUSTER_DIR" "$DATA_DIR"
    > "$CLUSTER_DIR/nodes"

    port=$BASE_PORT
    all_peers=""

    start_node() {
      local lang="$1" index="$2" p="$3" peers="$4"
      local store_dir="$DATA_DIR/${lang}-${index}"
      mkdir -p "$store_dir"

      if [[ "$lang" == "go" ]]; then
        "$ROOT/implementations/go/gpgchain-node" \
          --addr "0.0.0.0:${p}" \
          --store "${store_dir}/chain.db" \
          --peers "$peers" \
          --allow-all-domains \
          --node-url "http://localhost:${p}" \
          > "$store_dir/node.log" 2>&1 &
      else
        python "$ROOT/implementations/python/node.py" \
          --addr "0.0.0.0:${p}" \
          --store-dir "$store_dir" \
          --peers "$peers" \
          --allow-all-domains \
          --node-url "http://localhost:${p}" \
          > "$store_dir/node.log" 2>&1 &
      fi

      local pid=$!
      echo "${lang} ${index} ${p} ${pid}" >> "$CLUSTER_DIR/nodes"
      echo "  started ${lang} node ${index} on port ${p} (pid ${pid})"

      if [[ -z "$all_peers" ]]; then
        all_peers="http://localhost:${p}"
      else
        all_peers="${all_peers},http://localhost:${p}"
      fi
    }

    echo "==> Starting cluster: ${GO_COUNT} Go + ${PYTHON_COUNT} Python nodes"

    for i in $(seq 1 "$GO_COUNT"); do
      start_node go "$i" "$port" "$all_peers"
      ((port++))
    done

    for i in $(seq 1 "$PYTHON_COUNT"); do
      start_node python "$i" "$port" "$all_peers"
      ((port++))
    done

    echo "==> Cluster started. Run './scripts/cluster.sh status' to verify."
    ;;

  stop)
    if [[ ! -f "$CLUSTER_DIR/nodes" ]]; then
      echo "No cluster state found."
      exit 0
    fi
    while IFS=' ' read -r lang index port pid; do
      if kill "$pid" 2>/dev/null; then
        echo "  stopped ${lang} node ${index} (pid ${pid})"
      fi
    done < "$CLUSTER_DIR/nodes"
    rm -rf "$CLUSTER_DIR"
    echo "==> Cluster stopped."
    ;;

  status)
    if [[ ! -f "$CLUSTER_DIR/nodes" ]]; then
      echo "No cluster running."
      exit 0
    fi
    printf "%-10s %-8s %-8s %-8s %s\n" "LANGUAGE" "INDEX" "PORT" "PID" "STATUS"
    while IFS=' ' read -r lang index port pid; do
      if kill -0 "$pid" 2>/dev/null; then
        status="running"
      else
        status="dead"
      fi
      printf "%-10s %-8s %-8s %-8s %s\n" "$lang" "$index" "$port" "$pid" "$status"
    done < "$CLUSTER_DIR/nodes"
    ;;

  *) usage ;;
esac
