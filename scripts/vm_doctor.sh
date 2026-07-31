#!/usr/bin/env bash
# VM 봇 무반응 — 원인 진단 + (선택) 재시작
# Cloud Shell: bash scripts/cloudshell_bot.sh doctor
# VM 직접:   bash scripts/vm_doctor.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DO_RESTART="${1:-}"

echo "=== VM bot doctor ==="
echo "ROOT: $ROOT"
echo "git: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"

echo ""
echo "=== [1] 프로세스 ==="
if pgrep -af '[p]ython.*main\.py' >/dev/null 2>&1; then
  pgrep -af '[p]ython.*main\.py'
else
  echo "❌ main.py 프로세스 없음 — 봇 꺼짐"
fi

echo ""
echo "=== [2] bot.sh status ==="
bash scripts/bot.sh status || true

echo ""
echo "=== [3] 텔레그램 진단 ==="
bash scripts/diag_telegram.sh || true

echo ""
echo "=== [4] 최근 로그 ==="
bash scripts/bot.sh logs 2>/dev/null | tail -n 40 || true

if [[ "$DO_RESTART" == "restart" ]]; then
  echo ""
  echo "=== restart ==="
  bash scripts/bot.sh restart
  sleep 2
  bash scripts/bot.sh status || true
fi

echo ""
echo "=== doctor 완료 ==="
echo "텔레그램: /start → @봇이름 확인 (diag [3] getMe)"
echo "재시작: bash scripts/vm_doctor.sh restart"
