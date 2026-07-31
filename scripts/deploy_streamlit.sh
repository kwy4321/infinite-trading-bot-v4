#!/usr/bin/env bash
# VM Streamlit 최신 코드 반영 + 재시작 — Cloud Shell에서 실행
# bash scripts/deploy_streamlit.sh
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
REPO_URL="${REPO_URL:-https://github.com/kwy4321/infinite-trading-bot-v4.git}"

SSH_KEY="${SSH_KEY:-}"
for k in "$HOME"/ssh-key-*.key "$HOME"/*.pem; do
  [[ -f "$k" ]] && SSH_KEY="$k" && break
done
if [[ -z "${SSH_KEY:-}" || ! -f "$SSH_KEY" ]]; then
  echo "❌ ssh-key-*.key 없음 — Cloud Shell에 VM 생성 키 업로드"
  exit 1
fi

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"

echo "=== Streamlit 배포 → VM ${IP:-?} ==="
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 -i "$SSH_KEY" "${SSH_USER}@${IP}" bash -s -- "$INSTALL_DIR" "$REPO_URL" <<'REMOTE'
set -euo pipefail
INSTALL_DIR="$1"
REPO_URL="$2"
cd "$INSTALL_DIR"

echo "--- git pull ---"
git fetch origin main
git reset --hard origin/main
echo "commit: $(git rev-parse --short HEAD)"

echo "--- deps ---"
if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -q -U pip
  .venv/bin/pip install -q -r requirements.txt
else
  python3 -m pip install -q -r requirements.txt
fi

echo "--- restart ---"
sudo systemctl stop infinite-trading-dashboard 2>/dev/null || true
bash scripts/run_streamlit.sh restart
bash scripts/run_streamlit.sh status

curl -sf -o /dev/null -w "local → HTTP %{http_code}\n" --max-time 5 http://127.0.0.1:8501
REMOTE

echo ""
echo "✅ 배포 완료"
echo "터널: bash scripts/streamlit_cloudflare_tunnel.sh"
echo "봇:   bash scripts/cloudshell_bot.sh restart"
