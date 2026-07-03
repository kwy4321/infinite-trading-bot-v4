#!/usr/bin/env bash
# 서버에서 토스 CLOSED 주문 orderedAt 확인 (매매날짜 디버그)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SYMBOL="${1:-SOXL}"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found in $ROOT"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -q -r requirements.txt

python scripts/inspect_broker_fills.py "$SYMBOL"
