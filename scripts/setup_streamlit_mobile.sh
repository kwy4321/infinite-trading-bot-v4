#!/bin/bash
# 폰/LTE 대시보드 — nginx(80) 시도 → 실패 시 Streamlit :80 직접 실행
# VM SSH에서: bash scripts/setup_streamlit_mobile.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"
ENV_FILE="$INSTALL_DIR/.env"
PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || curl -4 -s --max-time 5 api.ipify.org 2>/dev/null || true)"
MOBILE_URL="http://${PUBLIC_IP:-VM공인IP}"

echo "=== Streamlit 모바일(:80) 설정 ==="
echo "경로: $INSTALL_DIR"

if ! sudo -n true 2>/dev/null; then
  echo "❌ sudo 권한 필요 — VM에 ubuntu 계정으로 SSH 접속 후 실행하세요."
  echo "   (Cloud Shell 창이 VM SSH가 아니면: ssh ubuntu@${PUBLIC_IP:-공인IP})"
  exit 1
fi

if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install -q -U pip
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

_set_url() {
  local url="$1"
  [[ -f "$ENV_FILE" ]] || return
  if grep -qE '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null; then
    sed -i.bak -E "s|^STREAMLIT_URL=.*|STREAMLIT_URL=$url|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    echo "STREAMLIT_URL=$url" >> "$ENV_FILE"
  fi
  echo "✅ STREAMLIT_URL=$url"
}

_ensure_streamlit_8501() {
  sudo systemctl stop infinite-trading-dashboard-port80 2>/dev/null || true
  sudo systemctl stop infinite-trading-dashboard 2>/dev/null || true
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart
  local i code
  for i in $(seq 1 12); do
    code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8501 2>/dev/null || echo 000)"
    if [[ "$code" =~ ^(200|301|302|304)$ ]]; then
      echo "✅ Streamlit :8501 OK"
      return 0
    fi
    sleep 2
  done
  echo "❌ Streamlit :8501 시작 실패 — bash scripts/run_streamlit.sh logs"
  return 1
}

_test_port80() {
  local code
  code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:80 2>/dev/null || echo 000)"
  [[ "$code" =~ ^(200|301|302|304)$ ]]
}

# 1) nginx 프록시 (8501 백엔드)
if _ensure_streamlit_8501; then
  if bash "$INSTALL_DIR/scripts/setup_nginx.sh"; then
    _set_url "$MOBILE_URL"
    echo ""
    echo "✅ nginx :80 → Streamlit :8501"
    echo "📱 폰: $MOBILE_URL"
    exit 0
  fi
  echo ""
  echo "⚠️  nginx 실패 — Streamlit을 :80 에 직접 실행합니다 (fallback)"
fi

# 2) Fallback — Streamlit :80 (root systemd)
bash "$INSTALL_DIR/scripts/run_streamlit.sh" stop 2>/dev/null || true
sudo systemctl stop infinite-trading-dashboard nginx 2>/dev/null || true
sudo systemctl disable infinite-trading-dashboard 2>/dev/null || true

sed "s|__DEPLOY_PATH__|$INSTALL_DIR|g" \
  "$INSTALL_DIR/deploy/infinite-trading-dashboard-port80.service.tpl" \
  | sudo tee /etc/systemd/system/infinite-trading-dashboard-port80.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable infinite-trading-dashboard-port80
sudo systemctl restart infinite-trading-dashboard-port80
sleep 4

if ! systemctl is-active infinite-trading-dashboard-port80 >/dev/null 2>&1; then
  echo "❌ :80 서비스 시작 실패"
  sudo journalctl -u infinite-trading-dashboard-port80 -n 40 --no-pager || true
  exit 1
fi

if _test_port80; then
  _set_url "$MOBILE_URL"
  echo ""
  echo "✅ Streamlit :80 직접 실행 (nginx 없음)"
  echo "📱 폰 Safari/Chrome: $MOBILE_URL"
  ss -tlnp 2>/dev/null | grep ':80 ' || true
  exit 0
fi

echo "❌ 로컬 :80 응답 없음"
sudo journalctl -u infinite-trading-dashboard-port80 -n 30 --no-pager || true
echo ""
echo "대안 (방화벽 무관 HTTPS): Cloud Shell에서"
echo "  bash scripts/streamlit_cloudflare_tunnel.sh"
exit 1
