#!/usr/bin/env bash
# 서버에서 텔레그램 연결 테스트 (.env 사용)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found in $ROOT"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_RAW="${TELEGRAM_ALLOWED_CHAT_IDS:-${CHAT_ID:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN is empty in .env"
  exit 1
fi
if [[ -z "$CHAT_RAW" ]]; then
  echo "ERROR: TELEGRAM_ALLOWED_CHAT_IDS is empty in .env"
  exit 1
fi

CHAT_ID="${CHAT_RAW%%,*}"
CHAT_ID="${CHAT_ID// /}"

echo "[1/2] getMe — bot token check..."
ME_JSON="$(curl -sf --connect-timeout 15 "https://api.telegram.org/bot${TOKEN}/getMe")"
if ! echo "$ME_JSON" | grep -q '"ok":true'; then
  echo "getMe FAILED"
  echo "$ME_JSON"
  exit 1
fi
USER_NAME="$(echo "$ME_JSON" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')"
echo "  OK: @${USER_NAME}"

echo "[2/2] sendMessage — chat_id ${CHAT_ID}..."
TEXT="Infinite Trading Bot v4 — 서버 텔레그램 테스트 OK $(date '+%Y-%m-%d %H:%M:%S %Z')"
SEND_JSON="$(curl -sf --connect-timeout 15 -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{\"chat_id\":\"${CHAT_ID}\",\"text\":\"${TEXT}\"}")"
if ! echo "$SEND_JSON" | grep -q '"ok":true'; then
  echo "sendMessage FAILED"
  echo "$SEND_JSON"
  exit 1
fi
echo "  OK"
echo ""
echo "Telegram test passed. Check your Telegram app."
