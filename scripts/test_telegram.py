"""Telegram connection test — uses .env TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if not (ROOT / ".env").is_file():
        print(f"ERROR: .env not found in {ROOT}")
        return 1

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", os.getenv("CHAT_ID", "")).strip()

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is empty in .env")
        return 1
    if not chat_raw:
        print("ERROR: TELEGRAM_ALLOWED_CHAT_IDS is empty in .env")
        return 1

    chat_id = chat_raw.split(",")[0].strip()

    print("[1/2] getMe — bot token check...")
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15
        ) as resp:
            me = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"getMe FAILED: {exc}")
        return 1

    if not me.get("ok"):
        print(f"getMe FAILED: {me}")
        return 1

    user = me["result"]
    print(f"  OK: @{user.get('username')} ({user.get('first_name')})")

    print(f"[2/2] sendMessage — chat_id {chat_id}...")
    text = (
        f"Infinite Trading Bot v4 — 텔레그램 연결 테스트 성공! "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    payload = json.dumps(
        {"chat_id": chat_id, "text": text},
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            send = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"sendMessage FAILED: {exc.read().decode()}")
        return 1

    if not send.get("ok"):
        print(f"sendMessage FAILED: {send}")
        return 1

    print(f"  OK: message_id={send['result']['message_id']}")
    print()
    print("텔레그램 테스트 완료. 텔레그램 앱에서 메시지를 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
