#!/usr/bin/env bash
# Oracle Cloud Shell — IP 입력 없이 VM에 봇 백그라운드 시작
# Cloud Shell을 꺼도 VM에서 계속 실행됨
# 사용: bash scripts/cloudshell_bot.sh start | stop | restart | status | logs | doctor | streamlit | streamlit-start | streamlit-doctor
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
for k in "$HOME"/ssh-key-*.key "$HOME"/*.pem "$HOME"/*.key; do
  _add_key "$k"
done
_add_key "$HOME/.ssh/id_rsa"

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

_sync_secrets() {
  echo "=== Cloud Shell → VM .env / Sheets JSON 동기화 ==="
  ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "${SSH_USER}@${IP}" "mkdir -p '$INSTALL_DIR/data'"
  if [[ -f "$ROOT/.env" ]]; then
    scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$ROOT/.env" "${SSH_USER}@${IP}:${INSTALL_DIR}/.env"
    echo "  .env 업로드"
    ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "${SSH_USER}@${IP}" bash -s -- "$INSTALL_DIR" <<'VERIFY'
set -euo pipefail
DIR="$1"
ENV="$DIR/.env"
if grep -qE '^(SUMMARIZER_API_KEY|GOOGLE_API_KEY)=[^[:space:]]' "$ENV" 2>/dev/null; then
  echo "  ✅ VM .env — AI 키 줄 확인됨"
else
  echo "  ❌ VM .env — SUMMARIZER_API_KEY 또는 GOOGLE_API_KEY 값 없음"
  echo "     Cloud Shell $ENV 를 PC .env 와 동일하게 맞춘 뒤 restart"
fi
VERIFY
  else
    echo "  .env 없음 (Cloud Shell $ROOT/.env)"
    echo "  ⚠️ PC에서 수정한 .env 는 Cloud Shell 로 업로드해야 VM에 반영됩니다"
  fi
  if [[ -f "$ROOT/data/gemini_api_key.txt" ]]; then
    scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$ROOT/data/gemini_api_key.txt" \
      "${SSH_USER}@${IP}:${INSTALL_DIR}/data/gemini_api_key.txt"
    echo "  data/gemini_api_key.txt 업로드 (브리핑 AI fallback)"
  fi
  local json=""
  for candidate in \
    "$ROOT/data/google-service-account.json" \
    "$ROOT/google-service-account.json" \
    "$HOME/google-service-account.json" \
    "$HOME"/Downloads/*service*account*.json \
    "$HOME"/*service*account*.json; do
    if [[ -f "$candidate" ]]; then
      json="$candidate"
      break
    fi
  done
  if [[ -n "$json" ]]; then
    scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$json" \
      "${SSH_USER}@${IP}:${INSTALL_DIR}/data/google-service-account.json"
    echo "  google-service-account.json 업로드 ($json)"
  else
    echo "  google-service-account.json 없음 — Cloud Shell에 JSON 업로드 필요"
  fi
  echo "=== VM 설정 확인 ==="
  ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "${SSH_USER}@${IP}" \
    "cd '$INSTALL_DIR' && bash scripts/check_env.sh" || true
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

case "$ACTION" in
  start|restart)
    git fetch origin main
    git reset --hard origin/main
    find "$INSTALL_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    ;;
  stop|kill)
    bash scripts/bot.sh "$ACTION"
    exit 0
    ;;
  status|logs)
    bash scripts/bot.sh "$ACTION"
    exit 0
    ;;
  doctor)
    bash scripts/vm_doctor.sh
    exit 0
    ;;
  streamlit)
    git fetch origin main
    git reset --hard origin/main
    bash scripts/setup_streamlit.sh || true
    sudo systemctl stop infinite-trading-dashboard 2>/dev/null || true
    bash scripts/run_streamlit.sh restart
    if [[ -x scripts/streamlit_doctor.sh ]]; then
      bash scripts/streamlit_doctor.sh
    else
      bash scripts/run_streamlit.sh status || true
      ss -tlnp | grep 8501 || true
      curl -sf -o /dev/null -w "127.0.0.1:8501 → HTTP %{http_code}\n" --max-time 5 http://127.0.0.1:8501 || true
    fi
    exit 0
    ;;
  streamlit-start)
    sudo systemctl stop infinite-trading-dashboard 2>/dev/null || true
    bash scripts/run_streamlit.sh restart
    bash scripts/run_streamlit.sh status || true
    exit 0
    ;;
esac

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
_sync_secrets
_run_remote

if [[ "$ACTION" == "streamlit" || "$ACTION" == "streamlit-start" || "$ACTION" == "streamlit-doctor" ]]; then
  echo ""
  echo "=== Streamlit (VM) ==="
  echo "브라우저: http://${IP}:8501"
  echo ""
  echo "⚠️  Cloud Shell에서 run_streamlit.sh 실행 ≠ VM 실행"
  echo "   VM에서 띄우려면: bash scripts/cloudshell_bot.sh streamlit"
  echo ""
  echo "외부 접속 테스트 (Cloud Shell → VM):"
  curl -sf -o /dev/null -w "  http://${IP}:8501 → HTTP %{http_code}\n" --max-time 8 "http://${IP}:8501" \
    || echo "  ❌ http://${IP}:8501 응답 없음 — Security List TCP 8501 / VM ufw 확인"
  echo ""
  echo "VM .env: STREAMLIT_URL=http://${IP}:8501"
  echo "진단: bash scripts/cloudshell_bot.sh streamlit-doctor"
fi

if [[ "$ACTION" == "start" || "$ACTION" == "restart" ]]; then
  echo ""
  echo "=== VM Toss probe ==="
  ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "${SSH_USER}@${IP}" \
    "cd '$INSTALL_DIR' && (test -x .venv/bin/python && .venv/bin/python || python3) scripts/probe_toss_token.py" || true
  echo ""
  echo "완료 — Cloud Shell을 꺼도 VM에서 봇이 계속 실행됩니다."
  echo "상태 확인: bash scripts/cloudshell_bot.sh status"
  echo "무반응: bash scripts/cloudshell_bot.sh doctor"
fi
