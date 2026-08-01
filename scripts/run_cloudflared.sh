#!/bin/bash
# Cloudflare 터널 start | stop | restart | status | url | ensure
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CF="$ROOT/data/cloudflared"
LOG="$ROOT/logs/cloudflared.log"
PIDFILE="$ROOT/data/cloudflared.pid"
URLFILE="$ROOT/data/cloudflared.url"
ENV_FILE="$ROOT/.env"
UNIT="infinite-trading-cloudflared"
RUN_USER="${SUDO_USER:-${USER:-ubuntu}}"
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

_save_url() {
  local url="$1"
  [[ -z "$url" ]] && return 1
  echo "$url" >"$URLFILE"
  if [[ -f "$ENV_FILE" ]] && grep -qE '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null; then
    sed -i.bak -E "s|^STREAMLIT_URL=.*|STREAMLIT_URL=$url|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  fi
}

_systemd_available() {
  command -v systemctl >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1
}

_systemd_active() {
  _systemd_available && systemctl is-active --quiet "$UNIT" 2>/dev/null
}

_nohup_running() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

_running() {
  _systemd_active || _nohup_running
}

_install_systemd() {
  [[ -x "$CF" ]] || {
    curl -fsSL -o "$CF" \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x "$CF"
  }
  sed "s|__DEPLOY_PATH__|$ROOT|g; s|__USER__|$RUN_USER|g" \
    "$ROOT/deploy/infinite-trading-cloudflared.service.tpl" \
    | sudo tee "/etc/systemd/system/${UNIT}.service" >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable "$UNIT" 2>/dev/null || true
}

_stop() {
  pkill -f "cloudflared tunnel --url http://127.0.0.1:8501" 2>/dev/null || true
  if _systemd_available; then
    sudo systemctl stop "$UNIT" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
}

_start_nohup() {
  mkdir -p "$ROOT/data" "$ROOT/logs"
  : > "$LOG"
  echo "cloudflared nohup 시작 → Streamlit :8501" >&2
  nohup "$CF" tunnel --loglevel info --no-autoupdate \
    --url http://127.0.0.1:8501 >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
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
  if _systemd_available; then
    _install_systemd
    echo "cloudflared systemd 시작 → Streamlit :8501" >&2
    sudo systemctl restart "$UNIT"
  else
    _start_nohup
  fi
}

_wait_url() {
  local i url=""
  for i in $(seq 1 45); do
    url="$(parse_url_from_file "$LOG" || true)"
    [[ -n "$url" ]] && { _save_url "$url"; echo "$url"; return 0; }
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
    if _running; then
      url="$(parse_url_from_file "$URLFILE" || parse_url_from_file "$LOG" || true)"
      [[ -n "$url" ]] && echo "$url" && exit 0
    fi
    _start
    _wait_url || { echo "❌ URL 추출 실패 — bash scripts/run_cloudflared.sh logs"; exit 1; }
    ;;
  stop) _stop; echo "cloudflared 중지" ;;
  restart) _start; _wait_url || exit 1 ;;
  ensure)
    if _running; then
      url="$(parse_url_from_file "$URLFILE" || parse_url_from_file "$LOG" || true)"
      [[ -n "$url" ]] && _save_url "$url"
      exit 0
    fi
    _start
    _wait_url >/dev/null || true
    ;;
  url)
    if [[ -f "$URLFILE" ]]; then cat "$URLFILE"; exit 0; fi
    parse_url_from_file "$LOG" || {
      grep '^STREAMLIT_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || exit 1
    }
    ;;
  status)
    if _systemd_active; then
      echo "✅ cloudflared systemd 실행 중"
    elif _nohup_running; then
      echo "✅ cloudflared nohup PID $(cat "$PIDFILE")"
    else
      echo "⏹ cloudflared 꺼짐"
      exit 0
    fi
    parse_url_from_file "$URLFILE" || parse_url_from_file "$LOG" \
      || echo "(URL 미확인 — run_cloudflared.sh url)"
    ;;
  logs)
    if _systemd_active; then
      sudo journalctl -u "$UNIT" -n 30 --no-pager 2>/dev/null || true
    fi
    tail -n 60 "$LOG" 2>/dev/null || echo "로그 없음"
    ;;
  *)
    echo "Usage: bash scripts/run_cloudflared.sh {start|stop|restart|status|url|logs|ensure}"
    exit 1
    ;;
esac
