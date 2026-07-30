#!/usr/bin/env bash
# VM에서 최신 main 반영 + 봇 재시작 (GitHub Actions / cloudshell_bot.sh 공용)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$ROOT}"

if [[ "$ROOT" != "$(cd "$INSTALL_DIR" && pwd)" ]]; then
  cd "$INSTALL_DIR"
fi

if [[ ! -d .git ]]; then
  echo "❌ git repo 없음: $INSTALL_DIR"
  exit 1
fi

echo "=== deploy: fetch origin/$BRANCH ==="
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

REV="$(git rev-parse --short HEAD)"
echo "=== deployed commit: $REV ==="

find "$ROOT" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

if grep -rq "아래 버튼으로 Google Sheets" tg/ 2>/dev/null; then
  echo "❌ 구 장부 안내 문구가 코드에 남아 있음 — 배포 중단"
  exit 1
fi

if [[ -f tg/ledger_redirect.py ]]; then
  echo "❌ tg/ledger_redirect.py 가 아직 존재 — 배포 중단"
  exit 1
fi

echo "=== bot restart ==="
bash scripts/bot.sh restart
sleep 2
bash scripts/bot.sh status || true

echo "✅ VM deploy 완료 ($REV)"
