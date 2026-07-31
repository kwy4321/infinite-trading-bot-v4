#!/bin/bash
# Oracle Cloud Shell — SSH 키 등록 + 접속 테스트
# bash scripts/oracle_cloud_shell_ssh_fix.sh
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

KEY="$HOME/.ssh/id_rsa"
if [[ ! -f "$KEY" ]]; then
  echo "개인키 없음 — 새 키 생성"
  ssh-keygen -t rsa -b 2048 -f "$KEY" -N ""
fi
PUBKEY="$(cat "${KEY}.pub")"
FINGERPRINT="$(echo "$PUBKEY" | awk '{print $2}' | tail -c 20)"

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"
if [[ -z "$IP" || "$IP" == "null" ]]; then
  IP="158.180.95.81"
fi

echo "=== 1) Cloud Shell 공개키 ==="
echo "fingerprint …${FINGERPRINT}"

echo "=== 2) VM metadata ssh_authorized_keys ==="
OLD="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data.metadata."ssh_authorized_keys"' --raw-output 2>/dev/null || true)"
if [[ "$OLD" == "null" || -z "$OLD" ]]; then
  OLD=""
  echo "(없음)"
else
  echo "$OLD"
fi

if echo "$OLD" | grep -qF "$(echo "$PUBKEY" | awk '{print $2}')"; then
  COMBINED="$OLD"
  echo "현재 Cloud Shell 키가 metadata에 이미 있음"
else
  if [[ -n "$OLD" ]]; then
    COMBINED="${OLD}"$'\n'"${PUBKEY}"
  else
    COMBINED="${PUBKEY}"
  fi
  echo "키 추가 예정"
fi

echo "=== 3) VM STOP (키 반영, 1~2분) ==="
STATE="$(oci compute instance get --instance-id "$INSTANCE_OCID" --query 'data."lifecycle-state"' --raw-output)"
if [[ "$STATE" == "RUNNING" ]]; then
  oci compute instance action --instance-id "$INSTANCE_OCID" --action STOP
  oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state STOPPED >/dev/null
fi

echo "=== 4) metadata 갱신 ==="
oci compute instance get --instance-id "$INSTANCE_OCID" --query 'data.metadata' --raw-output \
  | jq --arg keys "$COMBINED" '. + {"ssh_authorized_keys": $keys}' > /tmp/oci_meta.json
oci compute instance update --instance-id "$INSTANCE_OCID" --metadata file:///tmp/oci_meta.json

echo "=== 5) VM START ==="
oci compute instance action --instance-id "$INSTANCE_OCID" --action START
oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state RUNNING >/dev/null
echo "RUNNING — SSH 대기 35초..."
sleep 35

IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"
echo "VM IP: $IP"

echo "=== 6) SSH 접속 시도 ==="
for U in ubuntu opc; do
  echo "--- user: $U ---"
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=25 -i "$KEY" "${U}@${IP}" \
    'echo "SSH OK"; hostname; whoami'; then
    echo ""
    echo "✅ 성공"
    echo "  ssh -i ~/.ssh/id_rsa ${U}@${IP}"
    echo "  bash scripts/cloudshell_bot.sh streamlit-start"
    exit 0
  fi
done

echo "❌ SSH 실패 — OCI 콘솔 → Instance → Console connection 으로 VM 접속"
exit 1
