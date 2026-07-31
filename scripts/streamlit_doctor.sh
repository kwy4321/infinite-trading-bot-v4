#!/usr/bin/env bash
# Streamlit 외부 접속 진단 — VM에서: bash scripts/streamlit_doctor.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${STREAMLIT_PORT:-8501}"

echo "=== Streamlit doctor ==="
echo "HOST: $(hostname)"
echo "USER: $(whoami)"
echo "PWD:  $ROOT"

PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || curl -4 -s --max-time 5 api.ipify.org 2>/dev/null || true)"
echo "PUBLIC_IP: ${PUBLIC_IP:-?}"

echo ""
echo "=== [1] 프로세스 ==="
if pgrep -af '[s]treamlit run dashboard/streamlit_app.py' >/dev/null 2>&1; then
  pgrep -af '[s]treamlit run dashboard/streamlit_app.py'
else
  echo "❌ Streamlit 프로세스 없음"
  echo "   → bash scripts/run_streamlit.sh restart"
fi

echo ""
echo "=== [2] 포트 ($PORT) ==="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp | grep ":$PORT " || echo "❌ $PORT 에서 listen 안 함"
else
  netstat -tlnp 2>/dev/null | grep ":$PORT " || echo "❌ $PORT 에서 listen 안 함"
fi

echo ""
echo "=== [3] 로컬 HTTP ==="
curl -sf -o /dev/null -w "127.0.0.1:$PORT → HTTP %{http_code}\n" --max-time 5 "http://127.0.0.1:$PORT" \
  || echo "❌ 127.0.0.1:$PORT 응답 없음"

if [[ -n "$PUBLIC_IP" ]]; then
  echo ""
  echo "=== [4] 공인 IP (VM 내부에서) ==="
  curl -sf -o /dev/null -w "$PUBLIC_IP:$PORT → HTTP %{http_code}\n" --max-time 5 "http://$PUBLIC_IP:$PORT" \
    || echo "❌ $PUBLIC_IP:$PORT 응답 없음 (Security List / ufw 확인)"
fi

echo ""
echo "=== [5] ufw ==="
if command -v ufw >/dev/null 2>&1; then
  sudo ufw status 2>/dev/null || ufw status 2>/dev/null || echo "ufw 상태 확인 불가"
else
  echo "ufw 없음"
fi

echo ""
echo "=== [6] systemd ==="
if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active infinite-trading-dashboard 2>/dev/null \
    && systemctl status infinite-trading-dashboard --no-pager -l 2>/dev/null | head -n 12 \
    || echo "infinite-trading-dashboard 비활성"
fi

echo ""
echo "=== doctor 완료 ==="
echo "PC 브라우저: http://${PUBLIC_IP:-VM공인IP}:$PORT"
echo "Oracle: VCN → Subnet → Security List → Ingress TCP $PORT"
