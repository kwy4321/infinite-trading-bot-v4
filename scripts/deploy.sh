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

PYTHON="$ROOT/.venv/bin/python" bash scripts/check_python.sh

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet infinite-trading-bot 2>/dev/null; then
  if command -v sudo >/dev/null 2>&1 && [[ -x /usr/bin/sudo || -x /bin/sudo ]]; then
    sudo systemctl restart infinite-trading-bot
    echo "Service restarted."
  else
    echo "systemd active but sudo unavailable — run: bash scripts/run.sh"
  fi
elif command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files infinite-trading-bot.service &>/dev/null; then
  if command -v sudo >/dev/null 2>&1 && [[ -x /usr/bin/sudo || -x /bin/sudo ]]; then
    sudo systemctl start infinite-trading-bot
    echo "Service started."
  else
    echo "systemd unit found but sudo unavailable — run: bash scripts/run.sh"
  fi
else
  echo "No systemd service — start manually: bash scripts/run.sh"
fi

echo "Deploy done: $(git rev-parse --short HEAD)"
