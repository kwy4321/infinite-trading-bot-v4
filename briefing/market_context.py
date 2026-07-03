"""아침 브리핑용 미국장 거래일·휴장 판별 (토스 market-calendar)."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from broker.toss_client import TossClient

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")


def _fmt_us_date(iso: str) -> str:
    if not iso or len(iso) < 10:
        return iso or "—"
    try:
        d = datetime.date.fromisoformat(iso[:10])
        return f"{d.month}/{d.day}({_WEEKDAY_KO[d.weekday()]})"
    except ValueError:
        return iso[:10]


def get_briefing_market_context(broker: "TossClient | None") -> dict:
    """7시 KST 브리핑 — 직전 미국 정규장 마감일·휴장 여부.

    7시 KST는 미국장 마감(약 5~6시 KST) 직후이므로 지수는 항상
    토스 ``previousBusinessDay``(직전 마감일) 기준. ``today``에 정규장이
    없으면 휴장일로 표시한다.
    """
    kst_now = datetime.datetime.now(KST)
    ny_today = kst_now.astimezone(NY).date().isoformat()

    if broker is None or broker.dry_run:
        session = (kst_now.date() - datetime.timedelta(days=1)).isoformat()
        return {
            "session_date": session,
            "session_label": _fmt_us_date(session),
            "us_holiday": False,
            "holiday_date": None,
            "holiday_label": None,
        }

    try:
        cal = broker.get_us_market_calendar()
    except Exception:
        session = ny_today
        return {
            "session_date": session,
            "session_label": _fmt_us_date(session),
            "us_holiday": False,
            "holiday_date": None,
            "holiday_label": None,
        }

    today = cal.get("today") or {}
    prev_day = cal.get("previousBusinessDay") or {}
    today_date = str(today.get("date") or ny_today)
    today_open = today.get("regularMarket") is not None
    prev_date = str(prev_day.get("date") or "")
    prev_open = prev_day.get("regularMarket") is not None

    session_date = prev_date if prev_open else today_date
    us_holiday = not today_open

    return {
        "session_date": session_date,
        "session_label": _fmt_us_date(session_date),
        "us_holiday": us_holiday,
        "holiday_date": today_date if us_holiday else None,
        "holiday_label": _fmt_us_date(today_date) if us_holiday else None,
    }
