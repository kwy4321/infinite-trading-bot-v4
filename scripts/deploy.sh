#!/usr/bin/env bash
# 서버에서 pull + 의존성 갱신 + systemd 재시작 (GitHub Actions에서도 호출)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"

echo "Deploying in $ROOT (branch: $BRANCH)"

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -U pip -q
pip install --no-cache-dir -r requirements.txt -q

if systemctl is-active --quiet infinite-trading-bot 2>/dev/null; then
  sudo systemctl restart infinite-trading-bot
  echo "Service restarted."
elif systemctl list-unit-files infinite-trading-bot.service &>/dev/null; then
  sudo systemctl start infinite-trading-bot
  echo "Service started."
else
  echo "systemd service not found — run scripts/server_setup.sh first."
fi

echo "Deploy done: $(git rev-parse --short HEAD)"
