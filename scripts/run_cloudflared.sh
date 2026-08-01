#!/bin/bash
# Cloudflare 터널 start | stop | status | url
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CF="$ROOT/data/cloudflared"
LOG="$ROOT/logs/cloudflared.log"
PIDFILE="$ROOT/data/cloudflared.pid"
URLFILE="$ROOT/data/cloudflared.url"
ACTION="${1:-status}"

parse_url_from_file() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local url
  url="$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$f" 2>/dev/null | tail -n 1 || true)"
  if [[ -z "$url" ]]; then
    local host
    host="$(grep -oiE '[a-zA-Z0-9.-]+\.trycloudflare\.com' "$f" 2>/dev/null | tail -n 1 || true)"
    [[ -n "$host" ]] && url="https://${host}"
  fi
  [[ -n "$url" ]] && echo "$url"
}

_running() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

_stop() {
  pkill -f "cloudflared tunnel --url http://127.0.0.1:8501" 2>/dev/null || true
  sudo systemctl stop infinite-trading-cloudflared 2>/dev/null || true
  rm -f "$PIDFILE"
}

_start() {
  mkdir -p "$ROOT/data" "$ROOT/logs"
  if [[ ! -x "$CF" ]]; then
    curl -fsSL -o "$CF" \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x "$CF"
  fi
  _stop
  sleep 1
  : > "$LOG"
  echo "cloudflared 시작 → Streamlit :8501" >&2
  nohup "$CF" tunnel --loglevel info --no-autoupdate \
    --url http://127.0.0.1:8501 >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
}

_wait_url() {
  local i url=""
  for i in $(seq 1 45); do
    url="$(parse_url_from_file "$LOG" || true)"
    [[ -n "$url" ]] && { echo "$url" >"$URLFILE"; echo "$url"; return 0; }
    if ! _running; then
      echo "cloudflared 프로세스 종료됨" >&2
      tail -n 20 "$LOG" >&2 || true
      return 1
    fi
    sleep 2
  done
  return 1
}

case "$ACTION" in
  start)
    _start
    _wait_url || { echo "❌ URL 추출 실패 — bash scripts/run_cloudflared.sh logs"; exit 1; }
    ;;
  stop) _stop; echo "cloudflared 중지" ;;
  restart) _stop; sleep 1; _start; _wait_url || exit 1 ;;
  url)
    if [[ -f "$URLFILE" ]]; then cat "$URLFILE"; exit 0; fi
    parse_url_from_file "$LOG" || exit 1
    ;;
  status)
    if _running; then
      echo "✅ cloudflared PID $(cat "$PIDFILE")"
      parse_url_from_file "$LOG" || parse_url_from_file "$URLFILE" || echo "(URL 로그에서 미확인 — run_cloudflared.sh url)"
    else
      echo "⏹ cloudflared 꺼짐"
    fi
    ;;
  logs)
    tail -n 60 "$LOG" 2>/dev/null || echo "로그 없음"
    ;;
  *)
    echo "Usage: bash scripts/run_cloudflared.sh {start|stop|restart|status|url|logs}"
    exit 1
    ;;
esac
