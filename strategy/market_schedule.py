"""KST 기준 자동 LOC 접수 스케줄."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from strategy.order_planner import JOB_SCHEDULE_KST

KST = ZoneInfo("Asia/Seoul")


def loc_auto_submit_kst(us_date: str) -> datetime.datetime:
    """자동 LOC 접수 시각 — KST 18:05 고정."""
    d = datetime.date.fromisoformat(us_date)
    hour, minute = JOB_SCHEDULE_KST["premarket_loc"]["summer"]
    return datetime.datetime.combine(d, datetime.time(hour, minute), tzinfo=KST)


def regular_open_kst(us_date: str) -> datetime.datetime:
    """하위 호환 별칭."""
    return loc_auto_submit_kst(us_date)
