#!/usr/bin/env bash
# 서버에서 pull + 의존성 갱신 + systemd 재시작 (GitHub Actions에서도 호출)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"

echo "Deploying in $ROOT (branch: $BRANCH)"

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

find "$ROOT" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

if grep -rq "아래 버튼으로 Google Sheets" tg/ 2>/dev/null; then
  echo "ERROR: 구 장부 안내 문구가 코드에 남아 있음"
  exit 1
fi
if [[ -f tg/ledger_redirect.py ]]; then
  echo "ERROR: tg/ledger_redirect.py 가 아직 존재"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -U pip -q
pip install --no-cache-dir -r requirements.txt -q

PYTHON="$ROOT/.venv/bin/python" bash scripts/check_python.sh

echo "=== stop all bot processes ==="
bash scripts/kill_all_bots.sh

if grep -q "format_ledger_redirect" tg/handler.py 2>/dev/null; then
  echo "ERROR: handler.py still imports format_ledger_redirect"
  exit 1
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files infinite-trading-bot.service &>/dev/null; then
  if command -v sudo >/dev/null 2>&1 && [[ -x /usr/bin/sudo || -x /bin/sudo ]]; then
    sudo systemctl restart infinite-trading-bot
    echo "Service restarted."
  else
    echo "systemd unit found but sudo unavailable — bot.sh start"
    bash scripts/bot.sh start
  fi
else
  echo "No systemd service — bot.sh restart"
  bash scripts/bot.sh restart
fi

echo "Deploy done: $(git rev-parse --short HEAD)"
