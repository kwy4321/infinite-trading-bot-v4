#!/usr/bin/env bash
# Oracle Cloud Shell — IP 입력 없이 VM에 봇 백그라운드 시작
# Cloud Shell을 꺼도 VM에서 계속 실행됨
# 사용: bash scripts/cloudshell_bot.sh start | stop | restart | status | logs
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-start}"

CONF="$ROOT/deploy/oracle.instance"
if [[ -f "$CONF" ]]; then
  # shellcheck disable=SC1090
  source "$CONF"
fi

INSTANCE_OCID="${INSTANCE_OCID:-}"
INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/infinite-trading-bot-v4}"
REPO_URL="${REPO_URL:-https://github.com/kwy4321/infinite-trading-bot-v4.git}"
SSH_USER="${SSH_USER:-ubuntu}"

if [[ -z "$INSTANCE_OCID" ]]; then
  echo "INSTANCE_OCID 없음 — deploy/oracle.instance 확인"
  exit 1
fi

if ! command -v oci >/dev/null 2>&1; then
  echo "oci CLI 없음 — Oracle Cloud Shell에서 실행하세요"
  exit 1
fi

# SSH 키 후보 (id_rsa + 업로드한 VM 키 모두 시도)
declare -a KEY_CANDIDATES=()
_add_key() {
  local k="$1"
  [[ -f "$k" ]] || return 0
  local existing
  for existing in "${KEY_CANDIDATES[@]:-}"; do
    [[ "$existing" == "$k" ]] && return 0
  done
  KEY_CANDIDATES+=("$k")
}
[[ -n "${SSH_KEY:-}" ]] && _add_key "$SSH_KEY"
_add_key "$HOME/.ssh/id_rsa"
for k in "$HOME"/ssh-key-*.key "$HOME"/*.pem "$HOME"/*.key; do
  _add_key "$k"
done

if [[ ${#KEY_CANDIDATES[@]} -eq 0 ]]; then
  echo "SSH 키 없음 — Cloud Shell 키 생성 중..."
  ssh-keygen -t rsa -b 2048 -f "$HOME/.ssh/id_rsa" -N ""
  KEY_CANDIDATES+=("$HOME/.ssh/id_rsa")
fi

echo "=== VM 상태 확인 ==="
STATE="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data."lifecycle-state"' --raw-output 2>/dev/null || echo UNKNOWN)"
echo "lifecycle-state: $STATE"

if [[ "$STATE" == "STOPPED" ]]; then
  echo "VM 시작 중..."
  oci compute instance action --instance-id "$INSTANCE_OCID" --action START
  oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state RUNNING >/dev/null
  echo "RUNNING — SSH 대기 25초..."
  sleep 25
elif [[ "$STATE" != "RUNNING" ]]; then
  echo "VM 상태: $STATE — 콘솔에서 확인하세요"
  exit 1
fi

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"
if [[ -z "$IP" || "$IP" == "null" ]]; then
  echo "공인 IP 없음"
  exit 1
fi
echo "VM IP: $IP (자동 조회)"

SSH_KEY=""
SSH_USER=""
LAST_ERR=""

_try_ssh() {
  local key="$1" user="$2" cmd="$3"
  local err
  err="$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 -o BatchMode=yes \
    -i "$key" "${user}@${IP}" "$cmd" 2>&1)" && return 0
  LAST_ERR="$err"
  return 1
}

_connect() {
  local key user u
  for key in "${KEY_CANDIDATES[@]}"; do
    chmod 600 "$key" 2>/dev/null || true
    echo "  키 시도: $key"
    for u in ubuntu opc "$SSH_USER"; do
      [[ -z "$u" ]] && continue
      if _try_ssh "$key" "$u" "echo SSH_OK"; then
        SSH_KEY="$key"
        SSH_USER="$u"
        echo "  ✅ SSH OK — user=$SSH_USER"
        return 0
      fi
      echo "    user=$u 실패: ${LAST_ERR:-unknown}"
    done
  done
  return 1
}

_run_remote() {
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 -i "$SSH_KEY" "${SSH_USER}@${IP}" bash -s -- "$ACTION" "$INSTALL_DIR" "$REPO_URL" <<'REMOTE'
set -euo pipefail
ACTION="$1"
INSTALL_DIR="$2"
REPO_URL="$3"

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  echo "프로젝트 없음 — clone: $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
git pull -q

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  echo "⚠️ VM에 .env 없음 — SSH 접속 후 nano $INSTALL_DIR/.env 설정 필요"
fi

bash scripts/bot.sh "$ACTION"
REMOTE
}

echo "=== SSH 연결 ==="
if ! _connect; then
  echo ""
  echo "SSH 거절 — Cloud Shell 키를 VM에 등록합니다 (VM 재시작 1~2분)..."
  bash "$ROOT/scripts/oracle_register_ssh_key.sh" "$INSTANCE_OCID"
  IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
    --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"
  echo "VM IP: $IP"
  _add_key "$HOME/.ssh/id_rsa"
  if ! _connect; then
    echo ""
    echo "❌ SSH 여전히 실패"
    echo "마지막 오류: ${LAST_ERR:-없음}"
    echo "수동: bash scripts/oracle_cloud_shell_ssh_fix.sh"
    exit 1
  fi
fi

echo "=== bot.sh $ACTION (VM) ==="
_run_remote

echo ""
echo "완료 — Cloud Shell을 꺼도 VM에서 봇이 계속 실행됩니다."
echo "상태 확인: bash scripts/cloudshell_bot.sh status"
