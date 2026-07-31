#!/usr/bin/env bash
# VM 1회 설정 — Cloudflare 터널 systemd (재부팅 후에도 URL 유지 시도)
# VM에서: bash scripts/setup_cloudflared.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"

CF="$INSTALL_DIR/data/cloudflared"
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

if [[ ! -x "$CF" ]]; then
  echo "cloudflared 다운로드..."
  curl -fsSL -o "$CF" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CF"
fi

if command -v systemctl >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
  sed "s|__DEPLOY_PATH__|$INSTALL_DIR|g; s|__USER__|$RUN_USER|g" \
    "$INSTALL_DIR/deploy/infinite-trading-cloudflared.service.tpl" \
    | sudo tee /etc/systemd/system/infinite-trading-cloudflared.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable infinite-trading-cloudflared
  sudo systemctl restart infinite-trading-cloudflared
  echo "systemd: infinite-trading-cloudflared"
  sleep 8
fi

LOG="$INSTALL_DIR/logs/cloudflared.log"
URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -n 1 || true)"
if [[ -n "$URL" ]]; then
  ENV="$INSTALL_DIR/.env"
  touch "$ENV"
  if grep -qE '^STREAMLIT_URL=' "$ENV" 2>/dev/null; then
    sed -i "s|^STREAMLIT_URL=.*|STREAMLIT_URL=$URL|" "$ENV"
  else
    echo "STREAMLIT_URL=$URL" >> "$ENV"
  fi
  echo ""
  echo "✅ 터널 URL: $URL"
  echo "   .env STREAMLIT_URL 저장됨"
  echo "   봇 반영: bash scripts/bot.sh restart"
else
  echo "⚠️ URL 추출 실패 — tail $LOG"
  tail -n 20 "$LOG" 2>/dev/null || true
fi
