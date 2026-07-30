#!/usr/bin/env bash
# Oracle Cloud Shell — IP 입력 없이 VM에 봇 백그라운드 시작
# Cloud Shell을 꺼도 VM에서 계속 실행됨
# 사용: bash scripts/cloudshell_bot.sh start | stop | restart | status | logs
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:-start}"

# deploy/oracle.instance 또는 환경변수
CONF="$ROOT/deploy/oracle.instance"
if [[ -f "$CONF" ]]; then
  # shellcheck disable=SC1090
  source "$CONF"
fi

INSTANCE_OCID="${INSTANCE_OCID:-}"
INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/infinite-trading-bot-v4}"
SSH_USER="${SSH_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"

if [[ -z "$INSTANCE_OCID" ]]; then
  echo "INSTANCE_OCID 없음 — deploy/oracle.instance 확인"
  exit 1
fi

if [[ ! -f "$SSH_KEY" ]]; then
  for k in "$HOME"/ssh-key-*.key "$HOME"/*.pem "$HOME/.ssh/id_rsa"; do
    if [[ -f "$k" ]]; then
      SSH_KEY="$k"
      break
    fi
  done
fi

if [[ ! -f "$SSH_KEY" ]]; then
  echo "SSH 키 없음 — Cloud Shell에 VM 개인키 업로드 후 chmod 600"
  exit 1
fi
chmod 600 "$SSH_KEY" 2>/dev/null || true

if ! command -v oci >/dev/null 2>&1; then
  echo "oci CLI 없음 — Oracle Cloud Shell에서 실행하세요"
  exit 1
fi

echo "=== VM 상태 확인 ==="
STATE="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data."lifecycle-state"' --raw-output 2>/dev/null || echo UNKNOWN)"
echo "lifecycle-state: $STATE"

if [[ "$STATE" == "STOPPED" ]]; then
  echo "VM 시작 중..."
  oci compute instance action --instance-id "$INSTANCE_OCID" --action START
  oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state RUNNING >/dev/null
  echo "RUNNING — SSH 대기 20초..."
  sleep 20
elif [[ "$STATE" != "RUNNING" ]]; then
  echo "VM 상태: $STATE — 콘솔에서 확인하세요"
  exit 1
fi

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"
if [[ -z "$IP" || "$IP" == "null" ]]; then
  echo "공인 IP 없음 — VM RUNNING 상태인지 확인"
  exit 1
fi
echo "VM IP: $IP (자동 조회)"

_ssh() {
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=25 -i "$SSH_KEY" "${SSH_USER}@${IP}" "$@"
}

echo "=== SSH → bot.sh $ACTION ==="
for U in "$SSH_USER" ubuntu opc; do
  SSH_USER="$U"
  if _ssh "test -d '$INSTALL_DIR'" 2>/dev/null; then
    _ssh "cd '$INSTALL_DIR' && git pull -q && bash scripts/bot.sh '$ACTION'"
    echo ""
    echo "완료 — Cloud Shell을 꺼도 VM에서 봇이 계속 실행됩니다."
    echo "상태 확인: bash scripts/cloudshell_bot.sh status"
    exit 0
  fi
done

echo "SSH 실패 — 키/사용자 확인 (bash scripts/oracle_cloud_shell_ssh_fix.sh)"
exit 1
