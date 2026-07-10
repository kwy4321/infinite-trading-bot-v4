"""KST 기준 미국 본장 스케줄."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from strategy.order_planner import JOB_SCHEDULE_KST

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")


def _us_eastern_is_dst(us_date: datetime.date) -> bool:
    """미국 동부 서머타임 여부 (해당 거래일)."""
    noon = datetime.datetime.combine(us_date, datetime.time(12, 0), tzinfo=NY)
    return bool(noon.dst())


def regular_open_kst(us_date: str) -> datetime.datetime:
    """미국 본장 개장 시각 — KST 고정 (서머 22:30 / 윈터 23:30)."""
    d = datetime.date.fromisoformat(us_date)
    slot = JOB_SCHEDULE_KST["regular_open_loc"]
    key = "summer" if _us_eastern_is_dst(d) else "winter"
    hour, minute = slot[key]
    return datetime.datetime.combine(d, datetime.time(hour, minute), tzinfo=KST)
