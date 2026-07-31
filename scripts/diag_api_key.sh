#!/usr/bin/env bash
# VM에서 AI 키 인식 진단 (키 값 출력 안 함)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV="$ROOT/.env"
TXT="$ROOT/data/gemini_api_key.txt"

echo "=== AI key diagnostic ==="
echo "ROOT: $ROOT"
echo "git: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
echo ".env exists: $(test -f "$ENV" && echo yes || echo no)"
if [[ -f "$ENV" ]]; then
  if grep -qE '^(SUMMARIZER_API_KEY|GOOGLE_API_KEY)=' "$ENV"; then
    echo ".env AI line: yes"
    grep -E '^(SUMMARIZER_API_KEY|GOOGLE_API_KEY)=' "$ENV" | sed 's/=.*/=***/'
  else
    echo ".env AI line: NO"
  fi
  if grep -q 'AIza' "$ENV"; then
    echo ".env AIza pattern: yes"
  else
    echo ".env AIza pattern: no"
  fi
fi
echo "gemini_api_key.txt: $(test -f "$TXT" && echo yes || echo no)"
if [[ -f "$TXT" ]]; then
  n=$(tr -d '\r\n ' < "$TXT" | wc -c)
  echo "gemini_api_key.txt len: $n"
fi
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python3 -c "
from config.settings import probe_llm_key_in_env_file, resolve_summarizer_api_key, reload_settings
s = reload_settings()
k, src = resolve_summarizer_api_key(s.summarizer_provider)
p = probe_llm_key_in_env_file()
print('resolve:', bool(k), src or '-')
print('probe:', p)
"
else
  echo "venv 없음 — bash scripts/check_env.sh 실행"
fi
