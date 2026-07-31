#!/usr/bin/env bash
# Cloud Shell에서 VM .env AI 키만 빠르게 넣기 (붙여넣기 깨질 때)
# 사용:
#   bash scripts/set_vm_api_key.sh
#   → AIza... 키만 입력 후 Enter, Ctrl+D
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONF="$ROOT/deploy/oracle.instance"
if [[ -f "$CONF" ]]; then
  # shellcheck disable=SC1090
  source "$CONF"
fi
INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/infinite-trading-bot-v4}"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "❌ Cloud Shell $ROOT/.env 없음 — 먼저 PC .env 업로드"
  exit 1
fi

echo "=== API 키 한 줄 입력 (AIza... 붙여넣기 후 Enter, Ctrl+D) ==="
KEY="$(cat | tr -d '\r\n ')"
if [[ -z "$KEY" ]]; then
  echo "❌ 키가 비어 있음"
  exit 1
fi
if [[ ! "$KEY" =~ ^AIza ]]; then
  echo "⚠️ Gemini 키는 보통 AIza 로 시작합니다 — 그대로 진행합니다"
fi

# 기존 .env 유지 + SUMMARIZER_API_KEY 갱신
TMP="$(mktemp)"
grep -vE '^(SUMMARIZER_API_KEY|GOOGLE_API_KEY)=' "$ROOT/.env" > "$TMP" || true
printf '\nSUMMARIZER_API_KEY=%s\n' "$KEY" >> "$TMP"
mv "$TMP" "$ROOT/.env"
chmod 600 "$ROOT/.env"
mkdir -p "$ROOT/data"
printf '%s\n' "$KEY" > "$ROOT/data/gemini_api_key.txt"
chmod 600 "$ROOT/data/gemini_api_key.txt"
echo "✅ Cloud Shell .env + data/gemini_api_key.txt 저장됨"

echo "=== VM 반영 (restart) ==="
exec bash "$ROOT/scripts/cloudshell_bot.sh" restart
