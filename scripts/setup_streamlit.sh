#!/bin/bash
# Streamlit 대시보드 설치·실행 — VM: bash scripts/setup_streamlit.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"
VENV="$INSTALL_DIR/.venv"

echo "=== Streamlit 대시보드 설정 ==="
echo "경로: $INSTALL_DIR"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -U pip
"$VENV/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

PUBLIC_IP="$(curl -4 -s ifconfig.me 2>/dev/null || curl -4 -s api.ipify.org 2>/dev/null || true)"

if [[ -f "$INSTALL_DIR/.env" ]]; then
  if ! grep -qE '^STREAMLIT_URL=' "$INSTALL_DIR/.env" 2>/dev/null; then
    echo "" >> "$INSTALL_DIR/.env"
    echo "STREAMLIT_URL=http://${PUBLIC_IP:-VM공인IP}:8501" >> "$INSTALL_DIR/.env"
    echo "  .env 에 STREAMLIT_URL 추가함"
  fi
else
  echo "⚠️  .env 없음 — STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}:8501 수동 추가"
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
  sleep 2
  sudo systemctl status infinite-trading-dashboard --no-pager -l || true
else
  echo "sudo/systemd 없음 — run_streamlit.sh 로 백그라운드 실행"
  bash "$INSTALL_DIR/scripts/run_streamlit.sh" restart
fi

echo ""
if curl -sf -o /dev/null -w "HTTP %{http_code}\n" --max-time 5 http://127.0.0.1:8501; then
  echo "✅ Streamlit 로컬(127.0.0.1:8501) 응답 OK"
else
  echo "❌ 로컬 접속 실패 — bash scripts/run_streamlit.sh logs"
fi

echo ""
echo "=== 외부 접속 ==="
echo "브라우저: http://${PUBLIC_IP:-VM공인IP}:8501"
echo ""
echo "체크리스트:"
echo "  1) .env STREAMLIT_URL=http://${PUBLIC_IP:-VM공인IP}:8501"
echo "  2) Oracle/GCP 방화벽 TCP 8501 허용"
echo "  3) VM .env 반영: bash scripts/cloudshell_bot.sh restart"
echo "  4) (선택) STREAMLIT_PASSWORD=비밀번호"
