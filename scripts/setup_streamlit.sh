#!/bin/bash
# Streamlit 대시보드 설치·실행 — 봇 VM에서: bash scripts/setup_streamlit.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"
VENV="$INSTALL_DIR/.venv"

echo "=== Streamlit 대시보드 설정 ==="
echo "경로: $INSTALL_DIR"
echo "사용자: $RUN_USER"

if [[ ! -d "$VENV" ]]; then
  echo "가상환경 없음 — 생성 중..."
  python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  echo "⚠️  $INSTALL_DIR/.env 없음 — STREAMLIT_URL 등 설정 후 다시 실행하세요."
fi

grep -q '^STREAMLIT_URL=' "$INSTALL_DIR/.env" 2>/dev/null || \
  echo "⚠️  .env에 STREAMLIT_URL=http://$(curl -4 -s ifconfig.me 2>/dev/null || echo '공인IP'):8501 추가하세요."

sed "s|__DEPLOY_PATH__|$INSTALL_DIR|g; s|__USER__|$RUN_USER|g" \
  "$INSTALL_DIR/deploy/infinite-trading-dashboard.service.tpl" \
  | sudo tee /etc/systemd/system/infinite-trading-dashboard.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable infinite-trading-dashboard
sudo systemctl restart infinite-trading-dashboard

sleep 2
echo ""
echo "=== 서비스 상태 ==="
sudo systemctl status infinite-trading-dashboard --no-pager -l || true

echo ""
echo "=== 로컬 접속 테스트 ==="
if curl -sf -o /dev/null -w "HTTP %{http_code}\n" --max-time 5 http://127.0.0.1:8501; then
  echo "✅ Streamlit 로컬(127.0.0.1:8501) 응답 OK"
else
  echo "❌ 로컬 접속 실패 — journalctl -u infinite-trading-dashboard -n 50"
fi

PUBLIC_IP="$(curl -4 -s ifconfig.me 2>/dev/null || true)"
echo ""
echo "=== 외부 접속 체크리스트 ==="
echo "1) .env: STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}:8501"
echo "2) Ubuntu 방화벽: sudo ufw allow 8501/tcp && sudo ufw reload"
echo "3) Oracle Cloud: 콘솔 → VCN → Security List → Ingress Rule → TCP 8501 (0.0.0.0/0)"
echo "4) GCP: VPC 방화벽 tcp:8501 허용"
echo "5) 봇 재시작: sudo systemctl restart infinite-trading-bot"
echo ""
echo "브라우저: http://${PUBLIC_IP:-152.67.194.170}:8501"
