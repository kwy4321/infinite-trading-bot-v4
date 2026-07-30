#!/bin/bash
# Oracle Cloud Shell에서 통째로 실행 — SSH 키 등록 + 접속 테스트
# bash scripts/oracle_cloud_shell_ssh_fix.sh  (또는 아래 내용 copy-paste)

set -euo pipefail

INSTANCE_OCID="ocid1.instance.oc1.ap-chuncheon-1.an4w4ljrbhtvjlacu4tveiqge2kspspa22epoamqsvpu7s6ysdrrh4wai2nq"
IP="158.180.95.81"
PUBKEY='ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCPATnHL8pCVCgyAt/i1OerJGH9J4ztpUTInMEO+AsZfzHWRXl3o2oNmcclLKQz401+H/e5Fcdw5R6CozDiMwOQdEeC1S2kElzuge07sUwes79kOaZNczbZmuwGJJHNFbcJ1n5qvWmdTAR7TyjEJUO9aNNPJhgu2u50qZytcPQVV7Kuzl33i2OKc5m0vu33kl4+6haZv20g7L8C9xy8kN7T2BSXlljhVCmmoq6mQqIED7CjE2HW8TFi5RPRdLzGMZ0QjpJtZkh1enqt9i/s+vqcBY3V/ajSlrzOs/P00oqLwXIMrsIXlenDGmjQo1rX+h0a5OO+nEqSYveVynsHT21b kwy4321@10e682cced60'

KEY="$HOME/.ssh/id_rsa"
if [[ ! -f "$KEY" ]]; then
  echo "개인키 없음 — 새 키 생성"
  ssh-keygen -t rsa -b 2048 -f "$KEY" -N ""
  PUBKEY="$(cat "${KEY}.pub")"
fi

echo "=== 1) 기존 authorized_keys (metadata) ==="
OLD="$(oci compute instance get --instance-id "$INSTANCE_OCID" \
  --query 'data.metadata."ssh_authorized_keys"' --raw-output 2>/dev/null || true)"
if [[ "$OLD" == "null" || -z "$OLD" ]]; then
  OLD=""
fi
echo "${OLD:-"(없음)"}"

if echo "$OLD" | grep -qF "kwy4321@10e682cced60"; then
  COMBINED="$OLD"
  echo "Cloud Shell 키가 metadata에 이미 포함됨"
else
  if [[ -n "$OLD" ]]; then
    COMBINED="${OLD}"$'\n'"${PUBKEY}"
  else
    COMBINED="${PUBKEY}"
  fi
fi

echo "=== 2) 인스턴스 STOP (1~2분) ==="
STATE="$(oci compute instance get --instance-id "$INSTANCE_OCID" --query 'data."lifecycle-state"' --raw-output)"
if [[ "$STATE" == "RUNNING" ]]; then
  oci compute instance action --instance-id "$INSTANCE_OCID" --action STOP
  oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state STOPPED >/dev/null
fi

echo "=== 3) metadata에 SSH 키 등록 ==="
oci compute instance get --instance-id "$INSTANCE_OCID" --query 'data.metadata' --raw-output \
  | jq --arg keys "$COMBINED" '. + {"ssh_authorized_keys": $keys}' > /tmp/oci_meta.json
oci compute instance update --instance-id "$INSTANCE_OCID" --metadata file:///tmp/oci_meta.json

echo "=== 4) 인스턴스 START ==="
oci compute instance action --instance-id "$INSTANCE_OCID" --action START
oci compute instance get --instance-id "$INSTANCE_OCID" --wait-for-state RUNNING >/dev/null
echo "RUNNING — SSH 대기 30초..."
sleep 30

echo "=== 5) SSH 접속 시도 ==="
for U in ubuntu opc; do
  echo "--- user: $U ---"
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 -i "$KEY" "${U}@${IP}" \
    'echo "SSH OK"; hostname; whoami'; then
    echo ""
    echo "성공! 다음 명령으로 접속:"
    echo "  ssh -i ~/.ssh/id_rsa ${U}@${IP}"
    exit 0
  fi
done

echo "SSH 실패 — Console Connection 필요 (Oracle 콘솔 → Instance → Console connection)"
exit 1
