#!/bin/bash
# 폰/LTE용 — Cloudflare HTTPS 터널 (8501·80 방화벽 불필요)
# VM SSH: bash scripts/setup_streamlit_phone.sh
# Cloud Shell: bash scripts/cloudshell_bot.sh streamlit-phone
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"
ENV_FILE="$INSTALL_DIR/.env"
LOG="$INSTALL_DIR/logs/cloudflared.log"
CF="$INSTALL_DIR/data/cloudflared"

echo "=== Streamlit 폰용 HTTPS 터널 ==="

bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart
code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8501 2>/dev/null || echo 000)"
if [[ ! "$code" =~ ^(200|301|302|304)$ ]]; then
  echo "❌ Streamlit :8501 미응답 — bash scripts/run_streamlit.sh logs"
  exit 1
fi
echo "✅ Streamlit :8501 OK"

if [[ ! -x "$CF" ]]; then
  echo "cloudflared 다운로드..."
  mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
  curl -fsSL -o "$CF" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CF"
fi

pkill -f "cloudflared tunnel --url http://127.0.0.1:8501" 2>/dev/null || true
sudo systemctl stop infinite-trading-cloudflared 2>/dev/null || true
: > "$LOG"

sed "s|__DEPLOY_PATH__|$INSTALL_DIR|g; s|__USER__|$RUN_USER|g" \
  "$INSTALL_DIR/deploy/infinite-trading-cloudflared.service.tpl" \
  | sudo tee /etc/systemd/system/infinite-trading-cloudflared.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable infinite-trading-cloudflared
sudo systemctl restart infinite-trading-cloudflared

URL=""
for _ in $(seq 1 25); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -n 1 || true)"
  [[ -n "$URL" ]] && break
  sleep 2
done

if [[ -z "$URL" ]]; then
  echo "❌ HTTPS URL 추출 실패"
  tail -n 40 "$LOG" 2>/dev/null || sudo journalctl -u infinite-trading-cloudflared -n 30 --no-pager
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  if grep -qE '^STREAMLIT_URL=' "$ENV_FILE"; then
    sed -i.bak -E "s|^STREAMLIT_URL=.*|STREAMLIT_URL=$URL|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    echo "STREAMLIT_URL=$URL" >> "$ENV_FILE"
  fi
else
  echo "STREAMLIT_URL=$URL" > "$ENV_FILE"
fi

PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || true)"
echo ""
echo "============================================"
echo "📱 폰/LTE (Safari·Chrome):"
echo "   $URL"
echo ""
echo "💻 PC (:8501): http://${PUBLIC_IP:-공인IP}:8501"
echo "============================================"
echo ""
echo "✅ .env STREAMLIT_URL → HTTPS 터널"
grep '^STREAMLIT_URL=' "$ENV_FILE" || true
echo ""
echo "봇 반영: bash scripts/cloudshell_bot.sh restart"
echo "⚠️  VM 재부팅 후 터널 URL 바뀔 수 있음 → 이 스크립트 다시 실행"
