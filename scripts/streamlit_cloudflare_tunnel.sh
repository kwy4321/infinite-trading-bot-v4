#!/usr/bin/env bash
# Streamlit HTTPS 공개 URL — Cloud Shell: bash scripts/streamlit_cloudflare_tunnel.sh
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
  echo "❌ VM SSH 키 없음 — Cloud Shell에 ssh-key-*.key 업로드"
  exit 1
fi

chmod 600 "$SSH_KEY" 2>/dev/null || true
echo "=== Streamlit 폰용 HTTPS (Cloudflare) ==="
echo "VM: ${SSH_USER}@${IP:-?}"

ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 -i "$SSH_KEY" "${SSH_USER}@${IP}" bash -s -- "$INSTALL_DIR" <<'REMOTE'
set -euo pipefail
INSTALL_DIR="$1"
cd "$INSTALL_DIR"
git fetch origin main
git reset --hard origin/main
bash scripts/setup_streamlit_phone.sh
REMOTE

echo ""
echo "텔레그램 📈 대시보드 + bash scripts/cloudshell_bot.sh restart"
