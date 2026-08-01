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
    echo "⚠️  $url (PC/Wi-Fi만)"
    echo "   → 폰: bash scripts/setup_streamlit_phone.sh"
  elif echo "$url" | grep -q 'trycloudflare.com'; then
    echo "✅ $url (폰/LTE HTTPS OK)"
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
  local80_ok=0
  [[ "$code80" =~ ^(200|301|302|304)$ ]] && local80_ok=1

  if [[ "$local80_ok" == "1" ]]; then
    echo "✅ 서버 :80 준비됨 (로컬 $code80) — 폰 Safari/Chrome에서 테스트:"
    echo "   http://${PUBLIC_IP}"
  fi

  if [[ "$ext80" =~ ^(200|301|302|304)$ ]]; then
    echo "✅ http://${PUBLIC_IP} (:80) → $ext80"
  elif [[ "$local80_ok" == "1" ]]; then
    echo "⚠️  VM→공인IP :80 → $ext80 (OCI hairpin 또는 Security List TCP 80 — 폰에서 직접 열어보세요)"
  else
    echo "❌ http://${PUBLIC_IP} (:80) → $ext80"
  fi

  if [[ "$ext8501" =~ ^(200|301|302|304)$ ]]; then
    echo "✅ http://${PUBLIC_IP}:8501 → $ext8501 (PC/Wi-Fi용)"
  else
    echo "⚠️  http://${PUBLIC_IP}:8501 → $ext8501"
  fi
fi

echo ""
if [[ "${local80_ok:-0}" == "1" ]]; then
  echo "=== 결론 ==="
  echo "nginx/Streamlit 정상. ❌가 아니라 ⚠️ 이면 VM 자체 테스트 한계일 수 있음."
  echo "폰: http://${PUBLIC_IP:-공인IP} (Safari/Chrome, 텔레그램 내장 X)"
  echo "안 열리면 Oracle Security List Ingress TCP 80 재확인"
else
  echo "=== 8501만 열릴 때 (Oracle :80 미개방) ==="
  echo "PC: http://${PUBLIC_IP:-공인IP}:8501"
  echo "폰: bash scripts/setup_streamlit_phone.sh  (HTTPS, 방화벽 불필요)"
fi
echo ""
echo "--- Cloudflare HTTPS (폰/LTE) ---"
cf_env_url=""
[[ -f "$ENV_FILE" ]] && cf_env_url="$(grep '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
cf_running=0
bash "$INSTALL_DIR/scripts/run_cloudflared.sh" status 2>/dev/null | grep -q '✅' && cf_running=1

if [[ "$cf_running" == "1" ]]; then
  cf_url="$(bash "$INSTALL_DIR/scripts/run_cloudflared.sh" url 2>/dev/null || true)"
  [[ -z "$cf_url" && -n "$cf_env_url" ]] && cf_url="$cf_env_url"
  if [[ -n "$cf_url" ]]; then
    cf_code="$(_http_code "$cf_url")"
    if [[ "$cf_code" =~ ^(200|301|302|304)$ ]]; then
      echo "✅ 터널 실행 + HTTPS $cf_code"
      echo "📱 $cf_url"
    else
      echo "⚠️  터널 실행 중이나 HTTPS → $cf_code (잠시 후 재시도)"
      echo "📱 $cf_url"
    fi
  else
    echo "ℹ️  실행 중 — bash scripts/run_cloudflared.sh url"
  fi
elif echo "$cf_env_url" | grep -q 'trycloudflare.com'; then
  echo "❌ .env URL 있으나 터널 꺼짐 (폰 접속 불가)"
  echo "   $cf_env_url"
  echo "   → bash scripts/cloudshell_bot.sh streamlit-phone"
  echo ""
  echo "💡 우회: Oracle :8501 이 열려 있으면 폰 LTE에서도 시도:"
  echo "   http://${PUBLIC_IP:-공인IP}:8501"
else
  echo "ℹ️  미설정 — bash scripts/cloudshell_bot.sh streamlit-phone"
fi
echo ""
echo "Cloud Shell: bash scripts/cloudshell_bot.sh streamlit-phone"
