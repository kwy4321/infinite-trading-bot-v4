#!/usr/bin/env bash
# Cloud Shell 공개키를 VM metadata에 등록 (SSH 거절 시 자동 호출)
set -euo pipefail

INSTANCE_OCID="${1:-}"
if [[ -z "$INSTANCE_OCID" && -f deploy/oracle.instance ]]; then
  # shellcheck disable=SC1091
  source deploy/oracle.instance
fi
INSTANCE_OCID="${INSTANCE_OCID:-}"

if [[ -z "$INSTANCE_OCID" ]]; then
  echo "INSTANCE_OCID 필요"
  exit 1
fi

if ! command -v oci >/dev/null 2>&1; then
  echo "oci CLI 필요 (Oracle Cloud Shell)"
  exit 1
fi

if [[ ! -f "$HOME/.ssh/id_rsa" ]]; then
  echo "Cloud Shell SSH 키 생성..."
  ssh-keygen -t rsa -b 2048 -f "$HOME/.ssh/id_rsa" -N ""
fi
PUBKEY="$(cat "$HOME/.ssh/id_rsa.pub")"
FINGERPRINT="$(echo "$PUBKEY" | awk '{print $2}' | tail -c 20)"

echo "=== Cloud Shell 키 등록 (metadata) ==="
echo "⚠️  Oracle은 VM 생성 후 ssh_authorized_keys metadata 변경 불가"
echo "   이 스크립트만으로 SSH가 안 되면: bash scripts/oracle_console_ssh_fix.sh"
OLD="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data.metadata."ssh_authorized_keys"' --raw-output 2>/dev/null || true)"
if [[ "$OLD" == "null" ]]; then OLD=""; fi

if [[ -n "$OLD" ]] && echo "$OLD" | grep -qF "$PUBKEY"; then
  echo "키가 metadata에 이미 등록됨"
  exit 0
fi

if [[ -n "$OLD" ]]; then
  COMBINED="${OLD}"$'\n'"${PUBKEY}"
else
  COMBINED="${PUBKEY}"
fi

STATE="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data."lifecycle-state"' --raw-output)"
if [[ "$STATE" == "RUNNING" ]]; then
  echo "metadata 갱신을 위해 VM STOP (1~2분)..."
  oci compute instance action --instance-id "$INSTANCE_OCID" --action STOP
  oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state STOPPED >/dev/null
fi

oci compute instance get --instance-id "$INSTANCE_OCID" --query 'data.metadata' --raw-output \
  | jq --arg keys "$COMBINED" '. + {"ssh_authorized_keys": $keys}' > /tmp/oci_meta_keys.json
oci compute instance update --instance-id "$INSTANCE_OCID" --metadata file:///tmp/oci_meta_keys.json

echo "VM START..."
oci compute instance action --instance-id "$INSTANCE_OCID" --action START
oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state RUNNING >/dev/null
echo "RUNNING — SSH 대기 30초..."
sleep 30
echo "키 등록 완료 (fingerprint …${FINGERPRINT})"
