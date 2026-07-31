#!/usr/bin/env bash
# Streamlit HTTPS 공개 URL (방화벽 8501 불필요) — Cloud Shell에서 실행
# bash scripts/streamlit_cloudflare_tunnel.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f deploy/oracle.instance ]]; then
  # shellcheck disable=SC1091
  source deploy/oracle.instance
fi

INSTANCE_OCID="${INSTANCE_OCID:-}"
INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/infinite-trading-bot-v4}"
SSH_USER="${SSH_USER:-ubuntu}"

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"

SSH_KEY="${SSH_KEY:-}"
if [[ -z "$SSH_KEY" || ! -f "$SSH_KEY" ]]; then
  for k in "$HOME"/ssh-key-*.key "$HOME"/*.pem; do
    [[ -f "$k" ]] && SSH_KEY="$k" && break
  done
fi
if [[ -z "$SSH_KEY" || ! -f "$SSH_KEY" ]]; then
  echo "❌ VM SSH 키 없음 — Cloud Shell에 ssh-key-*.key 업로드 (VM 생성 때 받은 파일)"
  exit 1
fi

chmod 600 "$SSH_KEY" 2>/dev/null || true
echo "=== Streamlit + Cloudflare 터널 ==="
echo "SSH key: $SSH_KEY"
echo "VM: ${SSH_USER}@${IP:-?}"

ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 -i "$SSH_KEY" "${SSH_USER}@${IP}" bash -s -- "$INSTALL_DIR" <<'REMOTE'
set -euo pipefail
INSTALL_DIR="$1"
cd "$INSTALL_DIR"

echo "--- git pull ---"
git fetch origin main
git reset --hard origin/main
echo "commit: $(git rev-parse --short HEAD)"
if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -q -r requirements.txt
fi

# Streamlit
sudo systemctl stop infinite-trading-dashboard 2>/dev/null || true
bash scripts/run_streamlit.sh restart
if ! curl -sf --max-time 5 http://127.0.0.1:8501 >/dev/null; then
  echo "❌ Streamlit 로컬 응답 없음"
  bash scripts/run_streamlit.sh logs | tail -n 20
  exit 1
fi
echo "✅ Streamlit 127.0.0.1:8501 OK"

# cloudflared
CF="$INSTALL_DIR/data/cloudflared"
if [[ ! -x "$CF" ]]; then
  echo "cloudflared 다운로드..."
  curl -fsSL -o "$CF" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CF"
fi

pkill -f "cloudflared tunnel --url http://127.0.0.1:8501" 2>/dev/null || true
sleep 1
LOG="$INSTALL_DIR/logs/cloudflared.log"
mkdir -p "$INSTALL_DIR/logs"
nohup "$CF" tunnel --url http://127.0.0.1:8501 >>"$LOG" 2>&1 &
echo $! > "$INSTALL_DIR/data/cloudflared.pid"
sleep 8

URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | tail -n 1 || true)"
if [[ -z "$URL" ]]; then
  echo "❌ 터널 URL 추출 실패 — 로그:"
  tail -n 30 "$LOG" 2>/dev/null || true
  exit 1
fi

echo ""
echo "============================================"
echo "  PC 브라우저 (8501 방화벽 없이 접속):"
echo "  $URL"
echo "============================================"
echo ""
echo "VM .env STREAMLIT_URL (봇 재시작 필요):"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "${SSH_USER}@${IP}" bash -s -- "$URL" "$INSTALL_DIR" <<'ENVPATCH'
URL="$1"
DIR="$2"
ENV="$DIR/.env"
touch "$ENV"
if grep -qE '^STREAMLIT_URL=' "$ENV" 2>/dev/null; then
  sed -i "s|^STREAMLIT_URL=.*|STREAMLIT_URL=$URL|" "$ENV"
else
  echo "STREAMLIT_URL=$URL" >> "$ENV"
fi
grep STREAMLIT_URL "$ENV"
ENVPATCH
echo "봇 반영: bash scripts/cloudshell_bot.sh restart"
REMOTE

echo ""
echo "터널 유지 — Cloud Shell/VM 재부팅 시 다시 실행:"
echo "  bash scripts/streamlit_cloudflare_tunnel.sh"
