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
  echo "❌ Streamlit :8501 타임아웃 (70초)"
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" logs 2>/dev/null | tail -n 25 || true
  return 1
}

_fetch_cf_url() {
  local url=""
  url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -n 1 || true)"
  if [[ -n "$url" ]]; then
    echo "$url"
    return 0
  fi
  if command -v journalctl >/dev/null 2>&1; then
    url="$(sudo journalctl -u infinite-trading-cloudflared -n 80 --no-pager 2>/dev/null \
      | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
  fi
  [[ -n "$url" ]] && echo "$url"
}

# nginx :80 점유 시 8501과 무관 — Streamlit만 확인
if ! _wait_streamlit 2>/dev/null; then
  echo "Streamlit 재시작..."
  sudo systemctl stop infinite-trading-dashboard-port80 2>/dev/null || true
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart || bash "$INSTALL_DIR/scripts/run_streamlit.sh" start
  _wait_streamlit || exit 1
fi

if [[ ! -x "$CF" ]]; then
  echo "cloudflared 다운로드..."
  mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
  curl -fsSL -o "$CF" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CF"
fi

pkill -f "cloudflared tunnel --url http://127.0.0.1:8501" 2>/dev/null || true
sudo systemctl stop infinite-trading-cloudflared 2>/dev/null || true
mkdir -p "$INSTALL_DIR/logs"
: > "$LOG"

sed "s|__DEPLOY_PATH__|$INSTALL_DIR|g; s|__USER__|$RUN_USER|g" \
  "$INSTALL_DIR/deploy/infinite-trading-cloudflared.service.tpl" \
  | sudo tee /etc/systemd/system/infinite-trading-cloudflared.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable infinite-trading-cloudflared
sudo systemctl restart infinite-trading-cloudflared

URL=""
echo "Cloudflare URL 대기 중..."
for i in $(seq 1 40); do
  URL="$(_fetch_cf_url || true)"
  [[ -n "$URL" ]] && break
  if (( i % 5 == 0 )); then
    echo "   터널 대기 ($i/40)..."
  fi
  sleep 2
done

if [[ -z "$URL" ]]; then
  echo "❌ HTTPS URL 추출 실패 — cloudflared 로그:"
  tail -n 30 "$LOG" 2>/dev/null || true
  sudo journalctl -u infinite-trading-cloudflared -n 40 --no-pager 2>/dev/null || true
  echo ""
  echo "수동 시도: $CF tunnel --url http://127.0.0.1:8501"
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
