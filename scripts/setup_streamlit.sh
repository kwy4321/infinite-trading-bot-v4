#!/bin/bash
# Streamlit + nginx(80) — 모바일 LTE·텔레그램 폰 접속용
# VM: bash scripts/setup_streamlit.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"
VENV="$INSTALL_DIR/.venv"
ENV_FILE="$INSTALL_DIR/.env"

echo "=== Streamlit 대시보드 설정 ==="
echo "경로: $INSTALL_DIR"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -U pip
"$VENV/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || curl -4 -s --max-time 5 api.ipify.org 2>/dev/null || true)"
MOBILE_URL="http://${PUBLIC_IP:-VM공인IP}"

_set_streamlit_url() {
  local url="$1"
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "⚠️  .env 없음 — STREAMLIT_URL=$url 수동 추가"
    return
  fi
  if grep -qE '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null; then
    if grep -qE '^STREAMLIT_URL=.*(:8501|localhost|127\.0\.0\.1)' "$ENV_FILE" 2>/dev/null; then
      sed -i.bak -E "s|^STREAMLIT_URL=.*|STREAMLIT_URL=$url|" "$ENV_FILE"
      echo "✅ STREAMLIT_URL → $url (8501/localhost 제거 — 폰용)"
      rm -f "$ENV_FILE.bak"
    else
      echo "ℹ️  STREAMLIT_URL 유지 ($(grep '^STREAMLIT_URL=' "$ENV_FILE" | cut -d= -f2-))"
    fi
  else
    echo "" >> "$ENV_FILE"
    echo "STREAMLIT_URL=$url" >> "$ENV_FILE"
    echo "✅ .env에 STREAMLIT_URL=$url 추가"
  fi
}

_setup_nginx() {
  bash "$INSTALL_DIR/scripts/setup_nginx.sh"
}

if command -v ufw >/dev/null 2>&1; then
  if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    sudo ufw allow 8501/tcp comment 'Streamlit direct' 2>/dev/null || true
    sudo ufw allow 80/tcp comment 'Streamlit mobile nginx' 2>/dev/null || true
    sudo ufw reload 2>/dev/null || true
    echo "✅ ufw 80, 8501 허용"
  fi
fi

USE_SYSTEMD=0
if command -v systemctl >/dev/null 2>&1 \
  && command -v sudo >/dev/null 2>&1 \
  && { [[ -x /usr/bin/sudo ]] || [[ -x /bin/sudo ]]; }; then
  USE_SYSTEMD=1
fi

if [[ "$USE_SYSTEMD" == "1" ]]; then
  sed "s|__DEPLOY_PATH__|$INSTALL_DIR|g; s|__USER__|$RUN_USER|g" \
    "$INSTALL_DIR/deploy/infinite-trading-dashboard.service.tpl" \
    | sudo tee /etc/systemd/system/infinite-trading-dashboard.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable infinite-trading-dashboard
  sudo systemctl restart infinite-trading-dashboard
else
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart
fi

_wait_streamlit() {
  local i
  for i in $(seq 1 15); do
    if curl -sf -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:8501 2>/dev/null | grep -qE '^(200|301|302|304)$'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

echo ""
if _wait_streamlit; then
  echo "✅ Streamlit :8501 로컬 OK"
else
  echo "❌ Streamlit 로컬 실패 — bash scripts/run_streamlit.sh logs"
fi

NGINX_OK=0
if bash "$INSTALL_DIR/scripts/setup_nginx.sh"; then
  NGINX_OK=1
  _set_streamlit_url "$MOBILE_URL"
else
  echo "⚠️  nginx 설정 실패 — 위 오류 확인 후: bash scripts/setup_nginx.sh"
  echo "   PC만: http://${PUBLIC_IP:-VM공인IP}:8501"
fi

echo ""
echo "=== 접속 URL ==="
if [[ "$NGINX_OK" == "1" ]]; then
  echo "📱 폰 (권장): $MOBILE_URL  ← 포트 80, LTE OK"
  echo "💻 PC 직접:   http://${PUBLIC_IP:-VM공인IP}:8501"
else
  echo "http://${PUBLIC_IP:-VM공인IP}:8501"
fi
echo ""
echo "Oracle/GCP 방화벽: TCP 80 + 8501 Ingress 허용"
echo "폰: 텔레그램 버튼 → ⋯ → Safari/Chrome에서 열기 (내장 브라우저 X)"
echo "진단: bash scripts/check_streamlit.sh"
echo "봇: bash scripts/cloudshell_bot.sh restart"
