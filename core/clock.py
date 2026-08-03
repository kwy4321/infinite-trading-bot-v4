"""시간대·거래일 계산 단일 소스.

KST/NY ZoneInfo 와 미국 거래일 변환을 여기 한 곳에만 둔다.
(이전에는 8개 이상 모듈이 각자 ZoneInfo("Asia/Seoul") 를 선언했다.)
"""

from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

#: 자동 LOC 접수 시각 (KST) — 계획 18:00, 접수 18:05
LOC_SUBMIT_HHMM = (18, 5)
#: 장 마감 계획 브로드캐스트 시각 (KST)
PLAN_HHMM = (18, 0)


def now_kst() -> _dt.datetime:
    return _dt.datetime.now(KST)


def now_ny() -> _dt.datetime:
    return _dt.datetime.now(NY)


def today_kst() -> _dt.date:
    return now_kst().date()


def kst_date_str(when: _dt.datetime | None = None) -> str:
    return (when or now_kst()).astimezone(KST).date().isoformat()


def ny_date_str(when: _dt.datetime | None = None) -> str:
    return (when or now_kst()).astimezone(NY).date().isoformat()


def parse_iso(when: object) -> _dt.datetime | None:
    """ISO8601 문자열/datetime → tz-aware datetime. 실패 시 None."""
    if isinstance(when, _dt.datetime):
        return when if when.tzinfo else when.replace(tzinfo=KST)
    text = str(when or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def us_session_date(when: object) -> str:
    """체결 시각 → 그 체결이 속한 미국 거래일(ET 날짜). 실패 시 빈 문자열."""
    parsed = parse_iso(when)
    if parsed is None:
        return ""
    return parsed.astimezone(NY).date().isoformat()


def loc_auto_submit_kst(us_date: str) -> _dt.datetime:
    """해당 미국 거래일의 자동 LOC 접수 시각 (KST 18:05)."""
    day = _dt.date.fromisoformat(us_date)
    hour, minute = LOC_SUBMIT_HHMM
    return _dt.datetime.combine(day, _dt.time(hour, minute), tzinfo=KST)
