#!/usr/bin/env bash
# Cloud Shell / 로컬 — venv 준비 후 봇 실행 (sudo·systemctl 불필요)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -U pip -q
pip install --no-cache-dir -r requirements.txt -q

PYTHON="$ROOT/.venv/bin/python" bash scripts/check_python.sh

echo ""
echo "포그라운드 실행 중 (창 닫으면 종료됨)."
echo "백그라운드: bash scripts/bot.sh start"
echo "Cloud Shell → VM: bash scripts/cloudshell_bot.sh start"
echo ""

echo "Starting bot: $ROOT"
exec "$ROOT/.venv/bin/python" main.py
