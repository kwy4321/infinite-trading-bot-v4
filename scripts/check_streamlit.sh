#!/bin/bash
# Streamlit 모바일 접속 진단 — VM: bash scripts/check_streamlit.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$INSTALL_DIR/.env"
PUBLIC_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || curl -4 -s --max-time 5 icanhazip.com 2>/dev/null || true)"

_http_code() {
  curl -sf -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null || echo "000"
}

echo "=== Streamlit 접속 진단 ==="
echo "공인 IP: ${PUBLIC_IP:-알 수 없음}"
echo ""

echo "--- Streamlit :8501 ---"
if systemctl is-active infinite-trading-dashboard >/dev/null 2>&1; then
  echo "✅ systemd 서비스 실행 중"
elif ss -tlnp 2>/dev/null | grep -q ':8501'; then
  echo "ℹ️  systemd 아님 — run_streamlit.sh 로 :8501 실행 중 (정상)"
else
  echo "❌ Streamlit 미실행 — bash scripts/run_streamlit.sh start"
fi
ss -tlnp 2>/dev/null | grep ':8501' || echo "❌ 8501 리스닝 없음"
code8501="$(_http_code http://127.0.0.1:8501)"
[[ "$code8501" =~ ^(200|301|302|304)$ ]] && echo "✅ 로컬 :8501 → $code8501" || echo "❌ 로컬 :8501 → $code8501"

echo ""
echo "--- nginx / :80 (폰/LTE용) ---"
if systemctl is-active nginx >/dev/null 2>&1; then
  echo "✅ nginx 실행 중"
elif systemctl is-active infinite-trading-dashboard-port80 >/dev/null 2>&1; then
  echo "✅ Streamlit :80 직접 실행 (systemd)"
else
  echo "❌ :80 미설정 — bash scripts/setup_streamlit_mobile.sh"
fi
ss -tlnp 2>/dev/null | grep ':80 ' || echo "❌ 80 리스닝 없음"
code80="$(_http_code http://127.0.0.1:80)"
[[ "$code80" =~ ^(200|301|302|304)$ ]] && echo "✅ 로컬 :80 → $code80" || echo "❌ 로컬 :80 → $code80"

echo ""
echo "--- .env STREAMLIT_URL ---"
if [[ -f "$ENV_FILE" ]]; then
  url="$(grep '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  if [[ -z "$url" ]]; then
    echo "❌ 없음 → STREAMLIT_URL=http://${PUBLIC_IP:-공인IP}"
  elif echo "$url" | grep -q ':8501'; then
    echo "⚠️  $url"
    echo "   → 폰 LTE는 8501 차단 많음. setup_streamlit.sh 로 :80(nginx) 전환 권장"
  elif echo "$url" | grep -qE 'localhost|127\.0\.0\.1'; then
    echo "❌ localhost — 폰 불가: $url"
  else
    echo "✅ $url (폰용 URL 형식 OK)"
  fi
else
  echo "❌ .env 없음"
fi

echo ""
echo "--- 외부 접속 (VM→공인IP) ---"
if [[ -n "$PUBLIC_IP" ]]; then
  ext80="$(_http_code "http://${PUBLIC_IP}:80")"
  ext8501="$(_http_code "http://${PUBLIC_IP}:8501")"
  [[ "$ext80" =~ ^(200|301|302|304)$ ]] && echo "✅ http://${PUBLIC_IP} (:80) → $ext80" || echo "❌ http://${PUBLIC_IP} (:80) → $ext80 — VM 내부 curl은 000일 수 있음(OCI hairpin). 로컬 :80 확인"
  [[ "$ext8501" =~ ^(200|301|302|304)$ ]] && echo "✅ http://${PUBLIC_IP}:8501 → $ext8501" || echo "⚠️  http://${PUBLIC_IP}:8501 → $ext8501 (PC Wi-Fi만 될 수 있음)"
fi

echo ""
echo "=== 폰이 PC만 되고 안 될 때 ==="
echo "1) STREAMLIT_URL 포트 8501 → http://${PUBLIC_IP:-공인IP} (:80, nginx)"
echo "2) Oracle VCN Security List: TCP 80, 8501 Ingress"
echo "3) 텔레그램: 버튼 후 ⋯ → Safari/Chrome (내장 브라우저는 Streamlit WebSocket 실패)"
echo "4) LTE ↔ Wi-Fi 전환"
echo ""
echo "설정: bash scripts/setup_streamlit_mobile.sh"
echo "또는 Cloud Shell: bash scripts/cloudshell_bot.sh streamlit-mobile"
echo "대안(HTTPS): bash scripts/streamlit_cloudflare_tunnel.sh"
