#!/bin/bash
# 폰/LTE용 — Cloudflare HTTPS 터널 (8501·80 방화벽 불필요)
# Cloud Shell: bash scripts/cloudshell_bot.sh streamlit-phone
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
ENV_FILE="$INSTALL_DIR/.env"

echo "=== Streamlit 폰용 HTTPS 터널 ==="

_wait_streamlit() {
  local i code
  for i in $(seq 1 35); do
    code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8501 2>/dev/null || echo 000)"
    if [[ "$code" =~ ^(200|301|302|304)$ ]]; then
      echo "✅ Streamlit :8501 → HTTP $code"
      return 0
    fi
    if (( i <= 3 || i % 5 == 0 )); then
      echo "   Streamlit 기동 대기 ($i/35) HTTP $code..."
    fi
    sleep 2
  done
  echo "❌ Streamlit :8501 타임아웃"
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" logs 2>/dev/null | tail -n 25 || true
  return 1
}

if ! _wait_streamlit 2>/dev/null; then
  echo "Streamlit 재시작..."
  sudo systemctl stop infinite-trading-dashboard-port80 2>/dev/null || true
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart || bash "$INSTALL_DIR/scripts/run_streamlit.sh" start
  _wait_streamlit || exit 1
fi

echo "Cloudflare 터널 시작..."
URL="$(bash "$INSTALL_DIR/scripts/run_cloudflared.sh" restart)" || {
  bash "$INSTALL_DIR/scripts/run_cloudflared.sh" logs
  exit 1
}

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
grep '^STREAMLIT_URL=' "$ENV_FILE" || true
echo ""
echo "봇 반영: bash scripts/cloudshell_bot.sh restart"
echo "URL 재확인: bash scripts/run_cloudflared.sh url"
