#!/bin/bash
# Streamlit 모바일 접속 진단 — VM: bash scripts/check_streamlit.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$INSTALL_DIR/.env"
PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || curl -4 -s --max-time 5 icanhazip.com 2>/dev/null || true)"

echo "=== Streamlit 접속 진단 ==="
echo "경로: $INSTALL_DIR"
echo "공인 IP: ${PUBLIC_IP:-알 수 없음}"
echo ""

# 1. 서비스
echo "--- systemd ---"
if systemctl is-active infinite-trading-dashboard >/dev/null 2>&1; then
  echo "✅ infinite-trading-dashboard 실행 중"
else
  echo "❌ 서비스 중지 — bash scripts/setup_streamlit.sh"
fi

# 2. 포트 리스닝
echo ""
echo "--- 포트 8501 ---"
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep ':8501' || echo "❌ 8501 포트 리스닝 없음"
elif command -v netstat >/dev/null 2>&1; then
  netstat -tlnp 2>/dev/null | grep ':8501' || echo "❌ 8501 포트 리스닝 없음"
else
  echo "⚠️  ss/netstat 없음"
fi

# 3. 로컬 HTTP
echo ""
echo "--- 로컬 HTTP ---"
code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8501 2>/dev/null || echo '000')"
if [[ "$code" =~ ^(200|301|302|303|307|308)$ ]]; then
  echo "✅ http://127.0.0.1:8501 → HTTP $code"
else
  echo "❌ http://127.0.0.1:8501 → HTTP $code"
  echo "   journalctl -u infinite-trading-dashboard -n 40"
fi

# 4. .env STREAMLIT_URL
echo ""
echo "--- .env STREAMLIT_URL ---"
if [[ -f "$ENV_FILE" ]]; then
  url="$(grep '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  if [[ -z "$url" ]]; then
    echo "❌ STREAMLIT_URL 없음"
    echo "   → STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}:8501"
  elif echo "$url" | grep -qE 'localhost|127\.0\.0\.1|0\.0\.0\.0'; then
    echo "❌ localhost URL — 폰에서 접속 불가: $url"
    echo "   → STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}:8501"
  else
    echo "✅ $url"
  fi
  if grep -q '^STREAMLIT_PASSWORD=' "$ENV_FILE" 2>/dev/null; then
    echo "ℹ️  STREAMLIT_PASSWORD 설정됨 — 폰에서도 로그인 필요"
  fi
else
  echo "❌ .env 없음"
fi

# 5. ufw
echo ""
echo "--- 방화벽 (ufw) ---"
if command -v ufw >/dev/null 2>&1; then
  if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    if sudo ufw status 2>/dev/null | grep -q "8501"; then
      echo "✅ ufw 8501 허용됨"
    else
      echo "❌ ufw 8501 미허용 — sudo ufw allow 8501/tcp && sudo ufw reload"
    fi
  else
    echo "ℹ️  ufw 비활성"
  fi
else
  echo "ℹ️  ufw 없음"
fi

# 6. 외부 접속 (같은 VM에서 공인 IP로)
echo ""
echo "--- 외부 IP HTTP (VM→자기 공인IP) ---"
if [[ -n "$PUBLIC_IP" ]]; then
  ext_code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 10 "http://${PUBLIC_IP}:8501" 2>/dev/null || echo '000')"
  if [[ "$ext_code" =~ ^(200|301|302|303|307|308)$ ]]; then
    echo "✅ http://${PUBLIC_IP}:8501 → HTTP $ext_code"
  else
    echo "❌ http://${PUBLIC_IP}:8501 → HTTP $ext_code"
    echo "   Oracle/GCP Security List Ingress TCP 8501 (0.0.0.0/0) 확인"
    echo "   일부 통신사는 8501 포트 차단 — Wi-Fi/LTE 전환 시도"
  fi
else
  echo "⚠️  공인 IP 조회 실패"
fi

echo ""
echo "=== 요약 ==="
echo "폰 접속 URL: http://${PUBLIC_IP:-공인IP}:8501"
echo "텔레그램: 📈 대시보드 메뉴 (STREAMLIT_URL 설정 후)"
