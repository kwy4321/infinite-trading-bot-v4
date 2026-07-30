#!/usr/bin/env bash
# VM 텔레그램 연결 진단 — 반응 없을 때 실행
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "❌ .env 없음: $ROOT/.env"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_RAW="${TELEGRAM_ALLOWED_CHAT_IDS:-${CHAT_ID:-}}"

echo "=== [1] bot 프로세스 ==="
pgrep -af '[p]ython.*main\.py' || echo "(main.py 없음)"

echo ""
echo "=== [2] .env 텔레그램 ==="
if [[ -z "$TOKEN" ]]; then
  echo "❌ TELEGRAM_BOT_TOKEN 비어 있음"
else
  echo "TOKEN: ${TOKEN:0:8}...${TOKEN: -4}"
fi
echo "TELEGRAM_ALLOWED_CHAT_IDS: ${CHAT_RAW:-(비어 있음 — 모든 채팅 허용)}"

echo ""
echo "=== [3] getMe (토큰·봇 계정) ==="
ME="$(curl -sf --connect-timeout 15 "https://api.telegram.org/bot${TOKEN}/getMe" || true)"
if echo "$ME" | grep -q '"ok":true'; then
  USER="$(echo "$ME" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')"
  echo "✅ @${USER} — 이 봇에게 메시지 보내야 합니다"
else
  echo "❌ getMe 실패 (토큰 오류)"
  echo "$ME"
  exit 1
fi

echo ""
echo "=== [4] webhook (설정되면 polling 무반응) ==="
WH="$(curl -sf --connect-timeout 15 "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" || true)"
echo "$WH" | head -c 400
echo ""
if echo "$WH" | grep -q '"url":"http'; then
  echo "⚠️ webhook 활성 — 삭제 중..."
  curl -sf "https://api.telegram.org/bot${TOKEN}/deleteWebhook?drop_pending_updates=true" >/dev/null
  echo "✅ webhook 삭제됨 → bash scripts/bot.sh restart"
fi

echo ""
echo "=== [5] sendMessage 테스트 ==="
if [[ -z "$CHAT_RAW" ]]; then
  echo "⚠️ TELEGRAM_ALLOWED_CHAT_IDS 없음 — skip"
else
  bash "$ROOT/scripts/test_telegram.sh"
fi

echo ""
echo "=== 완료 ==="
echo "텔레그램에서 @${USER} 에 /myid 또는 /start 전송"
echo "chat_id 확인: /myid → .env TELEGRAM_ALLOWED_CHAT_IDS 와 일치해야 함"
