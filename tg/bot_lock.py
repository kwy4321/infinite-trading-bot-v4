"""Ensure only one bot process polls Telegram (Linux VM)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def acquire_bot_lock(root: Path | None = None) -> object | None:
    """Return open lock file (must stay alive) or None on non-Linux."""
    base = root or Path(__file__).resolve().parents[1]
    lock_path = base / "data" / "bot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:
        return None

    fp = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error(
            "봇이 이미 실행 중입니다 (%s). "
            "VM에서: bash scripts/kill_all_bots.sh && bash scripts/bot.sh start",
            lock_path,
        )
        fp.close()
        raise SystemExit(1)
    fp.write(str(os.getpid()))
    fp.flush()
    return fp
