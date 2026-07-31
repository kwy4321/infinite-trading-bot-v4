#!/usr/bin/env bash
# Cloud Shell / VM — Toss Open API 키만 안전하게 .env 에 반영
# 사용:
#   bash scripts/set_vm_toss_keys.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV="${ENV_PATH:-$ROOT/.env}"
if [[ ! -f "$ENV" ]]; then
  echo "❌ .env 없음: $ENV"
  exit 1
fi

echo "=== Toss Open API 키 입력 ==="
echo "WTS → 설정 → Open API 에서 복사 (따옴표·콤마 없이)"
echo ""
read -r -p "TOSS_CLIENT_ID (tsck_live_…): " CLIENT_ID
read -r -s -p "TOSS_CLIENT_SECRET (tsck_live_…, ID와 다른 값): " CLIENT_SECRET
echo ""

CLIENT_ID="$(printf '%s' "$CLIENT_ID" | tr -d '\r\n ')"
CLIENT_SECRET="$(printf '%s' "$CLIENT_SECRET" | tr -d '\r\n ')"
CLIENT_ID="${CLIENT_ID%,;}"
CLIENT_SECRET="${CLIENT_SECRET%,;}"

if [[ -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
  echo "❌ ID 또는 SECRET 이 비어 있음"
  exit 1
fi

TMP="$(mktemp)"
grep -vE '^(TOSS_CLIENT_ID|TOSS_CLIENT_SECRET|TOSS_API_KEY|TOSS_SECRET_KEY|TOSS_API_SECRET|TOSS_API_ID|TOSS_KEY|TOSS_SECRET)=' "$ENV" > "$TMP" || true
{
  printf 'TOSS_CLIENT_ID=%s\n' "$CLIENT_ID"
  printf 'TOSS_CLIENT_SECRET=%s\n' "$CLIENT_SECRET"
} >> "$TMP"
mv "$TMP" "$ENV"
chmod 600 "$ENV"

echo "✅ .env 갱신 — ID 앞 4자: ${CLIENT_ID:0:4}… (len=${#CLIENT_ID}), SECRET len=${#CLIENT_SECRET}"

if command -v systemctl >/dev/null 2>&1 && systemctl is-active infinite-trading-bot &>/dev/null; then
  echo "=== systemd 재시작 ==="
  sudo systemctl restart infinite-trading-bot
fi

echo "=== 토큰 발급 테스트 ==="
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/probe_toss_token.py" || true
else
  python3 "$ROOT/scripts/probe_toss_token.py" || true
fi
