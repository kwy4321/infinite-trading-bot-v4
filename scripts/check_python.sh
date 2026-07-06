#!/usr/bin/env bash
# 문법·import 검사 — 로컬·CI·배포 직전 공통
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
echo "check_python: $($PYTHON --version) @ $ROOT"

"$PYTHON" -m compileall -q .
"$PYTHON" -c "import main; print('import main: OK')"

echo "check_python: all passed"
