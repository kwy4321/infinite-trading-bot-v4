#!/bin/bash
# Streamlit 대시보드 설치·실행 + 모바일 접속 설정
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

if [[ -f "$ENV_FILE" ]]; then
  if ! grep -qE '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null; then
    echo "" >> "$ENV_FILE"
    echo "STREAMLIT_URL=http://${PUBLIC_IP:-VM공인IP}:8501" >> "$ENV_FILE"
    echo "✅ .env에 STREAMLIT_URL 추가"
  else
    current="$(grep '^STREAMLIT_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")"
    if echo "$current" | grep -qE 'localhost|127\.0\.0\.1|0\.0\.0\.0'; then
      echo "⚠️  STREAMLIT_URL이 localhost 계열 — 폰 접속 불가"
      echo "   → STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}:8501 로 수정"
    fi
  fi
else
  echo "⚠️  .env 없음 — STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}:8501 수동 추가"
fi

if command -v ufw >/dev/null 2>&1; then
  if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    if ! sudo ufw status 2>/dev/null | grep -q "8501"; then
      sudo ufw allow 8501/tcp comment 'Streamlit dashboard' || true
      sudo ufw reload || true
      echo "✅ ufw 8501/tcp 허용"
    fi
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
  sudo systemctl status infinite-trading-dashboard --no-pager -l || true
else
  echo "sudo/systemd 없음 — run_streamlit.sh 로 백그라운드 실행"
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
  echo "✅ Streamlit 로컬(127.0.0.1:8501) 응답 OK"
else
  echo "❌ 로컬 접속 실패"
  if [[ "$USE_SYSTEMD" == "1" ]]; then
    sudo journalctl -u infinite-trading-dashboard -n 40 --no-pager 2>/dev/null || true
    sudo systemctl stop infinite-trading-dashboard 2>/dev/null || true
  fi
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart || true
  _wait_streamlit && echo "✅ run_streamlit.sh 폴백 OK" || echo "로그: bash scripts/run_streamlit.sh logs"
fi

if [[ -n "$PUBLIC_IP" ]] && command -v ss >/dev/null 2>&1; then
  echo ""
  ss -tlnp 2>/dev/null | grep ':8501' || true
fi

echo ""
echo "=== 모바일 접속 ==="
echo "📱 http://${PUBLIC_IP:-공인IP}:8501"
echo "📈 텔레그램: 📈 대시보드 메뉴"
echo "진단: bash scripts/check_streamlit.sh"
echo "봇 재시작: bash scripts/cloudshell_bot.sh restart"
