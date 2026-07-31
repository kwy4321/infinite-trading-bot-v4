#!/usr/bin/env bash
# Streamlit 대시보드 — start | stop | restart | status | logs
# VM (sudo 없어도): bash scripts/run_streamlit.sh start
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PIDFILE="$ROOT/data/streamlit.pid"
LOGFILE="$ROOT/logs/streamlit.log"
PORT="${STREAMLIT_PORT:-8501}"
ACTION="${1:-status}"

mkdir -p "$ROOT/data" "$ROOT/logs"

_venv_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  else
    echo "python3"
  fi
}

_running() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

_start() {
  if _running; then
    echo "✅ Streamlit 이미 실행 중 (PID $(cat "$PIDFILE"), http://127.0.0.1:$PORT)"
    return 0
  fi
  PY="$(_venv_python)"
  if [[ ! -x "$ROOT/.venv/bin/streamlit" ]] && [[ "$PY" == "$ROOT/.venv/bin/python" ]]; then
    "$PY" -m pip install -q -r "$ROOT/requirements.txt"
  fi
  STREAMLIT="$ROOT/.venv/bin/streamlit"
  if [[ ! -x "$STREAMLIT" ]]; then
    STREAMLIT="streamlit"
  fi
  echo "Streamlit 시작 → http://0.0.0.0:$PORT (log: $LOGFILE)"
  nohup "$STREAMLIT" run dashboard/streamlit_app.py \
    --server.port="$PORT" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 4
  if _running; then
    echo "✅ 실행 중 (PID $(cat "$PIDFILE"))"
  else
    echo "❌ 시작 실패 — tail $LOGFILE"
    tail -n 30 "$LOGFILE" 2>/dev/null || true
    exit 1
  fi
}

_stop() {
  if _running; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    sleep 1
    rm -f "$PIDFILE"
    echo "Streamlit 중지"
  else
    pkill -f "streamlit run dashboard/streamlit_app.py" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "Streamlit 프로세스 없음"
  fi
}

case "$ACTION" in
  start) _start ;;
  stop|kill) _stop ;;
  restart) _stop; sleep 1; _start ;;
  status)
    if _running; then
      echo "✅ Streamlit 실행 중 (PID $(cat "$PIDFILE"), port $PORT)"
    else
      echo "⏹ Streamlit 꺼짐 — bash scripts/run_streamlit.sh start"
    fi
    ;;
  logs)
    if command -v systemctl >/dev/null 2>&1 \
      && systemctl is-active infinite-trading-dashboard >/dev/null 2>&1; then
      journalctl -u infinite-trading-dashboard -n 80 --no-pager 2>/dev/null || true
      echo "---"
    fi
    tail -n 80 "$LOGFILE" 2>/dev/null || echo "로그 없음: $LOGFILE"
    ;;
  *)
    echo "Usage: bash scripts/run_streamlit.sh {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
