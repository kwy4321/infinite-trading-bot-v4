#!/bin/bash
# nginx :80 → Streamlit :8501 (폰/LTE용) — VM: bash scripts/setup_nginx.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
CONF_SRC="$INSTALL_DIR/deploy/nginx-streamlit.conf.tpl"
CONF_DST="/etc/nginx/sites-available/streamlit-dashboard"

echo "=== nginx :80 프록시 설정 ==="

if [[ ! -f "$CONF_SRC" ]]; then
  echo "❌ $CONF_SRC 없음 — git pull 후 재시도"
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx 설치 중..."
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
fi

# 80 포트 점유 프로세스 확인
if ss -tlnp 2>/dev/null | grep -q ':80 '; then
  if ! ss -tlnp 2>/dev/null | grep ':80 ' | grep -q nginx; then
    echo "⚠️  80 포트를 다른 프로세스가 사용 중:"
    ss -tlnp 2>/dev/null | grep ':80 ' || true
    echo "   (apache 등 중지 후 재실행: sudo systemctl stop apache2 2>/dev/null; sudo systemctl disable apache2 2>/dev/null)"
  fi
fi

sudo cp "$CONF_SRC" "$CONF_DST"
sudo ln -sf "$CONF_DST" /etc/nginx/sites-enabled/streamlit-dashboard
sudo rm -f /etc/nginx/sites-enabled/default

echo "--- nginx 설정 테스트 ---"
sudo nginx -t

sudo systemctl enable nginx
sudo systemctl restart nginx
sleep 2

if ! systemctl is-active nginx >/dev/null 2>&1; then
  echo "❌ nginx 시작 실패"
  sudo systemctl status nginx --no-pager -l || true
  sudo journalctl -u nginx -n 30 --no-pager || true
  exit 1
fi

if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  sudo ufw allow 80/tcp comment 'Streamlit nginx' 2>/dev/null || true
  sudo ufw reload 2>/dev/null || true
fi

code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:80 2>/dev/null || echo 000)"
if [[ "$code" =~ ^(200|301|302|304)$ ]]; then
  echo "✅ nginx :80 → HTTP $code"
  ss -tlnp 2>/dev/null | grep ':80 ' || true
else
  echo "❌ 로컬 :80 → HTTP $code"
  echo "   Streamlit :8501 실행 확인: bash scripts/run_streamlit.sh status"
  exit 1
fi

PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || true)"
echo ""
echo "📱 폰 접속: http://${PUBLIC_IP:-공인IP}"
echo "   (Oracle Ingress TCP 80 이미 추가했다면 외부에서도 OK)"
