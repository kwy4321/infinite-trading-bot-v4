#!/usr/bin/env bash
# OCI Streamlit 포트 외부 접속 — Security List + VM ufw
# Cloud Shell: bash scripts/oracle_fix_port_8501.sh 80
#            bash scripts/oracle_fix_port_8501.sh 8501
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f deploy/oracle.instance ]]; then
  # shellcheck disable=SC1091
  source deploy/oracle.instance
fi

INSTANCE_OCID="${INSTANCE_OCID:-}"
# 첫 인자가 숫자면 포트, 아니면 IP
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
  PORT="$1"
  IP="${2:-158.180.95.81}"
else
  PORT="${STREAMLIT_PORT:-8501}"
  IP="${1:-158.180.95.81}"
fi

if [[ -z "$INSTANCE_OCID" ]]; then
  echo "INSTANCE_OCID 없음"
  exit 1
fi

echo "=== OCI 포트 $PORT 진단 ==="
IP_OCI="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."public-ip"' --raw-output 2>/dev/null || true)"
echo "공인 IP (OCI): ${IP_OCI:-?}"
echo "테스트 IP: $IP"

SUBNET_ID="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[0]."subnet-id"' --raw-output)"
NSG_IDS="$(oci compute instance list-vnics --instance-id "$INSTANCE_OCID" \
  --query 'data[*]."nsg-ids"[]' --raw-output 2>/dev/null || true)"

echo "Subnet: $SUBNET_ID"
echo "NSG: ${NSG_IDS:-없음}"

SL_IDS="$(oci network subnet get --subnet-id "$SUBNET_ID" \
  --query 'data."security-list-ids"[]' --raw-output)"

_add_8501_sl() {
  local sl_id="$1"
  echo ""
  echo "--- Security List: $sl_id ---"
  oci network security-list get --security-list-id "$sl_id" \
    --query 'data."ingress-security-rules"[*].{d:description,src:source,p:protocol,tcp:tcpOptions.destinationPortRange}' \
    --output table 2>/dev/null || true

  oci network security-list get --security-list-id "$sl_id" \
    --query 'data."ingress-security-rules"' > /tmp/ingress.json

  python3 << PY
import json
port = $PORT
with open("/tmp/ingress.json") as f:
    rules = json.load(f)
found = False
for r in rules:
    if r.get("protocol") != "6":
        continue
    tcp = r.get("tcpOptions") or {}
    pr = tcp.get("destinationPortRange") or {}
    lo, hi = pr.get("min"), pr.get("max")
    if lo is not None and hi is not None and lo <= port <= hi:
        found = True
        break
if not found:
    rules.append({
        "description": f"Streamlit {port}",
        "source": "0.0.0.0/0",
        "protocol": "6",
        "sourceType": "CIDR_BLOCK",
        "isStateless": False,
        "tcpOptions": {"destinationPortRange": {"min": port, "max": port}}
    })
    print(f"  → {port} 규칙 추가")
else:
    print(f"  → {port} 규칙 이미 있음")
with open("/tmp/ingress_new.json", "w") as f:
    json.dump(rules, f)
PY

  oci network security-list update \
    --security-list-id "$sl_id" \
    --ingress-security-rules file:///tmp/ingress_new.json \
    --force >/dev/null
  echo "  → 업데이트 완료"
}

while IFS= read -r sl; do
  [[ -n "$sl" ]] && _add_8501_sl "$sl"
done <<< "$SL_IDS"

if [[ -n "$NSG_IDS" ]]; then
  while IFS= read -r nsg; do
    [[ -z "$nsg" ]] && continue
    echo ""
    echo "--- NSG: $nsg ---"
    oci network nsg rules add --nsg-id "$nsg" --security-rules "[{
      \"direction\": \"INGRESS\",
      \"protocol\": \"6\",
      \"source\": \"0.0.0.0/0\",
      \"sourceType\": \"CIDR_BLOCK\",
      \"isStateless\": false,
      \"description\": \"Streamlit $PORT\",
      \"tcpOptions\": {\"destinationPortRange\": {\"min\": $PORT, \"max\": $PORT}}
    }]" 2>/dev/null && echo "  → NSG 규칙 추가" || echo "  → NSG 규칙 있거나 추가 실패(무시)"
  done <<< "$NSG_IDS"
fi

echo ""
echo "=== VM iptables / ufw (SSH 필요) ==="
KEY=""
for k in "$HOME"/ssh-key-*.key "$HOME/.ssh/id_rsa"; do
  [[ -f "$k" ]] && KEY="$k" && break
done

if [[ -n "$KEY" ]]; then
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 -i "$KEY" "ubuntu@${IP_OCI:-$IP}" bash -s "$PORT" <<'VMFIX' || true
set -euo pipefail
PORT="$1"
echo "ufw:"
sudo ufw allow "${PORT}"/tcp 2>/dev/null || true
sudo ufw status 2>/dev/null || echo "  (ufw 없음)"
echo ""
echo "iptables INPUT (상위 15줄):"
sudo iptables -L INPUT -n --line-numbers 2>/dev/null | head -n 15 || true
if sudo iptables -L INPUT -n 2>/dev/null | grep -q "REJECT\|DROP"; then
  echo "  → iptables REJECT/DROP 있음 — ${PORT} 허용 추가"
  sudo iptables -I INPUT 1 -p tcp --dport ${PORT} -j ACCEPT 2>/dev/null || true
  if command -v netfilter-persistent >/dev/null 2>&1; then
    sudo netfilter-persistent save 2>/dev/null || true
  fi
fi
echo ""
echo "listen:"
ss -tlnp | grep ":${PORT} " || true
echo ""
curl -sf -o /dev/null -w "127.0.0.1:${PORT} → %{http_code}\n" --max-time 5 "http://127.0.0.1:${PORT}" || true
curl -sf -o /dev/null -w "공인IP:${PORT} → %{http_code}\n" --max-time 5 "http://$(curl -4 -s ifconfig.me):${PORT}" 2>/dev/null || echo "공인IP curl 실패"
VMFIX
else
  echo "SSH 키 없음 — VM에서 수동: sudo ufw allow ${PORT}/tcp"
fi

echo ""
echo "=== 외부 curl (30초 후) ==="
sleep 10
curl -sf -o /dev/null -w "http://${IP_OCI:-$IP}:${PORT} → HTTP %{http_code}\n" --max-time 15 "http://${IP_OCI:-$IP}:${PORT}" \
  || echo "❌ 여전히 실패 — PC에서 SSH 터널 사용 (아래)"
echo ""
echo "=== PC 임시 우회 (SSH 터널) ==="
echo "PC PowerShell (ssh-key 파일 경로 지정):"
echo "  ssh -i C:\\path\\to\\ssh-key.key -L 8501:127.0.0.1:8501 ubuntu@${IP_OCI:-$IP}"
echo "  브라우저: http://localhost:8501"
