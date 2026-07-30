#!/usr/bin/env bash
# VM에서 봇 백그라운드 실행 — SSH/터미널 종료해도 유지
# 사용: bash scripts/bot.sh start | stop | restart | status | logs
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PIDFILE="$ROOT/data/bot.pid"
LOGDIR="$ROOT/logs"
LOGFILE="$LOGDIR/bot.log"
ACTION="${1:-status}"

mkdir -p "$ROOT/data" "$LOGDIR"

_venv_ready() {
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --no-cache-dir -U pip -q
  pip install --no-cache-dir -r requirements.txt -q
  PYTHON="$ROOT/.venv/bin/python" bash scripts/check_python.sh
}

_pid() {
  if [[ -f "$PIDFILE" ]]; then
    cat "$PIDFILE"
  fi
}

_running() {
  local pid
  pid="$(_pid 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

_systemd_available() {
  command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files infinite-trading-bot.service &>/dev/null 2>&1 \
    && command -v sudo >/dev/null 2>&1 \
    && { [[ -x /usr/bin/sudo ]] || [[ -x /bin/sudo ]]; }
}

_start_systemd() {
  echo "systemd infinite-trading-bot 시작..."
  sudo systemctl enable infinite-trading-bot 2>/dev/null || true
  sudo systemctl restart infinite-trading-bot
  sleep 1
  sudo systemctl --no-pager -l status infinite-trading-bot || true
}

_stop_systemd() {
  if _systemd_available && systemctl is-active --quiet infinite-trading-bot 2>/dev/null; then
    sudo systemctl stop infinite-trading-bot
    echo "systemd infinite-trading-bot 중지"
  fi
}

_start_nohup() {
  if _running; then
    echo "이미 실행 중 (PID $(_pid), log: $LOGFILE)"
    return 0
  fi
  _venv_ready
  echo "백그라운드 시작 → $LOGFILE"
  nohup "$ROOT/.venv/bin/python" main.py >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 1
  if _running; then
    echo "✅ 실행 중 (PID $(_pid))"
  else
    echo "❌ 시작 실패 — tail $LOGFILE"
    tail -n 30 "$LOGFILE" 2>/dev/null || true
    exit 1
  fi
}

_stop_nohup() {
  if _running; then
    kill "$(_pid)" 2>/dev/null || true
    sleep 1
    if _running; then
      kill -9 "$(_pid)" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
    echo "nohup 봇 중지"
  fi
}

case "$ACTION" in
  start)
    if _systemd_available; then
      _start_systemd
    else
      _start_nohup
    fi
    ;;
  stop)
    _stop_systemd
    _stop_nohup
    ;;
  restart)
    "$0" stop
    sleep 1
    "$0" start
    ;;
  status)
    if _systemd_available && systemctl is-active --quiet infinite-trading-bot 2>/dev/null; then
      sudo systemctl --no-pager -l status infinite-trading-bot || true
      exit 0
    fi
    if _running; then
      echo "✅ nohup 실행 중 (PID $(_pid), log: $LOGFILE)"
      exit 0
    fi
    echo "⏹ 봇 꺼짐"
    exit 1
    ;;
  logs)
    if _systemd_available && systemctl list-unit-files infinite-trading-bot.service &>/dev/null; then
      sudo journalctl -u infinite-trading-bot -n 80 --no-pager 2>/dev/null || true
    fi
    if [[ -f "$LOGFILE" ]]; then
      echo "--- $LOGFILE ---"
      tail -n 80 "$LOGFILE"
    else
      echo "로그 없음: $LOGFILE"
    fi
    ;;
  *)
    echo "Usage: bash scripts/bot.sh {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
