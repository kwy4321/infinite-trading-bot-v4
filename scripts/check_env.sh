#!/usr/bin/env bash
# Google Sheets / .env 설정 확인 (venv 자동 사용)
# 사용: bash scripts/check_env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "❌ .env 없음: $ROOT/.env"
  echo "   nano .env 로 TELEGRAM / GOOGLE_SHEETS 설정 후 다시 실행"
  exit 2
fi

if [[ ! -d .venv ]]; then
  echo "venv 생성 중..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -q python-dotenv 2>/dev/null || pip install --no-cache-dir -q -r requirements.txt

exec python scripts/check_env.py "$@"
