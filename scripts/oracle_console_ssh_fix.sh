#!/usr/bin/env bash
# OCI VM SSH 복구 — metadata 키 변경은 생성 후 불가 → Console Connection 또는 원본 키 사용
# Cloud Shell: bash scripts/oracle_console_ssh_fix.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f deploy/oracle.instance ]]; then
  # shellcheck disable=SC1091
  source deploy/oracle.instance
fi

INSTANCE_OCID="${INSTANCE_OCID:-}"
if [[ -z "$INSTANCE_OCID" ]]; then
  echo "INSTANCE_OCID 없음 — deploy/oracle.instance 확인"
  exit 1
fi

if ! command -v oci >/dev/null 2>&1; then
  echo "oci CLI 필요 (Oracle Cloud Shell)"
  exit 1
fi

[[ -f "$HOME/.ssh/id_rsa" ]] || ssh-keygen -t rsa -b 2048 -f "$HOME/.ssh/id_rsa" -N ""
PUB="$HOME/.ssh/id_rsa.pub"
PRIV="$HOME/.ssh/id_rsa"

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"

echo "=== OCI SSH 진단 ==="
echo "VM IP: ${IP:-?}"
echo ""
echo "⚠️  Oracle은 VM 생성 후 metadata ssh_authorized_keys 변경 불가"
echo "   oracle_register_ssh_key.sh 는 새 키 등록에 효과 없음"
echo ""

echo "=== [1] VM 생성 시 등록된 공개키 (metadata) ==="
META_KEYS="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data.metadata."ssh_authorized_keys"' --raw-output 2>/dev/null || true)"
if [[ "$META_KEYS" == "null" || -z "$META_KEYS" ]]; then
  echo "(metadata에 키 없음)"
else
  echo "$META_KEYS"
fi

echo ""
echo "=== [2] Cloud Shell 로컬 키 ==="
echo "공개키:"
cat "$PUB"
echo ""
echo "지문: $(ssh-keygen -lf "$PUB" 2>/dev/null || true)"

echo ""
echo "=== [3] 후보 private key 로 SSH 시도 ==="
FOUND=0
_try() {
  local key="$1" user="$2"
  [[ -f "$key" ]] || return 1
  chmod 600 "$key" 2>/dev/null || true
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes \
    -i "$key" "${user}@${IP}" 'echo SSH_OK' 2>/dev/null; then
    echo "✅ 성공 — key=$key user=$user"
    echo "   ssh -i $key ${user}@${IP}"
    FOUND=1
    return 0
  fi
  return 1
}

for key in "$HOME"/ssh-key-*.key "$HOME"/*.pem "$HOME"/*.key "$PRIV"; do
  for user in ubuntu opc; do
    _try "$key" "$user" && break 2 || true
  done
done

if [[ "$FOUND" == "1" ]]; then
  exit 0
fi

echo "❌ 등록된 private key로 SSH 실패"
echo ""
echo "=== [4] 해결: OCI Console Connection (콘솔 UI) ==="
echo "1) OCI → Compute → Instances → infi-trading-bot"
echo "2) 왼쪽 Resources → Console connection → Create console connection"
echo "3) Public key 붙여넣기 (아래 한 줄 전체):"
echo ""
cat "$PUB"
echo ""
echo "4) Create 후 「Launch Cloud Shell connection」 또는 SSH 명령으로 접속"
echo "5) ubuntu 로그인 후 실행:"
echo ""
echo "   mkdir -p ~/.ssh && chmod 700 ~/.ssh"
echo "   echo '$(cat "$PUB")' >> ~/.ssh/authorized_keys"
echo "   chmod 600 ~/.ssh/authorized_keys"
echo ""
echo "6) Cloud Shell에서 다시:"
echo "   ssh -i ~/.ssh/id_rsa ubuntu@${IP} 'echo SSH_OK'"
echo ""
echo "=== [5] (CLI) Console Connection 생성 ==="
CONN_JSON="$(oci compute instance-console-connection create \
  --instance-id "$INSTANCE_OCID" \
  --ssh-public-key-file "$PUB" 2>/dev/null || true)"
if [[ -n "$CONN_JSON" ]]; then
  echo "$CONN_JSON" | jq -r '.data."connection-string" // empty' 2>/dev/null || echo "$CONN_JSON"
  echo ""
  echo "위 connection-string 으로 serial console 접속 → authorized_keys 수동 추가"
else
  echo "Console connection CLI 실패 — 콘솔 UI 사용"
fi

exit 1
