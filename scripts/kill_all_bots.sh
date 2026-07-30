#!/usr/bin/env bash
# VM에서 돌아가는 모든 봇(main.py) 프로세스 강제 종료 — 좀비·중복 인스턴스 정리
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== kill_all_bots: ROOT=$ROOT ==="

_stop_systemd() {
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi
  if systemctl list-unit-files infinite-trading-bot.service &>/dev/null 2>&1; then
    if systemctl is-active --quiet infinite-trading-bot 2>/dev/null; then
      echo "systemd stop infinite-trading-bot"
      sudo systemctl stop infinite-trading-bot 2>/dev/null \
        || systemctl stop infinite-trading-bot 2>/dev/null \
        || true
    fi
  fi
}

_kill_pid() {
  local pid="$1"
  local sig="${2:-TERM}"
  kill "-$sig" "$pid" 2>/dev/null || true
}

_kill_pidfile() {
  local pf="$ROOT/data/bot.pid"
  if [[ -f "$pf" ]]; then
    local pid
    pid="$(cat "$pf" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      echo "pidfile kill $pid"
      _kill_pid "$pid" TERM
      sleep 1
      _kill_pid "$pid" KILL
    fi
    rm -f "$pf"
  fi
  rm -f "$ROOT/data/bot.lock" 2>/dev/null || true
}

_kill_matching_python() {
  local pass="$1"
  local sig="${2:-TERM}"
  local found=0
  while read -r pid cmd; do
    [[ -z "${pid:-}" ]] && continue
    if echo "$cmd" | grep -qE '(\.venv/bin/python|python3?) .*main\.py|infinite-trading-bot'; then
      echo "[$pass/$sig] PID $pid — ${cmd:0:120}"
      _kill_pid "$pid" "$sig"
      found=1
    fi
  done < <(ps -eo pid=,args= 2>/dev/null | grep -E '[p]ython.*main\.py' || true)
  return "$found"
}

_stop_systemd
_kill_pidfile

for pass in 1 2 3; do
  _kill_matching_python "pass$pass" TERM || true
  sleep 1
done

for pass in 1 2; do
  _kill_matching_python "force$pass" KILL || true
  sleep 1
done

REMAINING="$(ps -eo pid=,args= 2>/dev/null | grep -E '[p]ython.*main\.py' || true)"
if [[ -n "$REMAINING" ]]; then
  echo "❌ WARNING: main.py 프로세스가 아직 남아 있음:"
  echo "$REMAINING"
  exit 1
fi

echo "✅ 모든 bot(main.py) 프로세스 종료됨"
