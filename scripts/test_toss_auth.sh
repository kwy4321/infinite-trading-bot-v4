#!/usr/bin/env bash
# 서버에서 Toss OAuth 토큰 발급·캐시·401 재시도 테스트
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found in $ROOT"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -q -r requirements.txt

python scripts/test_toss_auth.py
