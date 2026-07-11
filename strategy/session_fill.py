"""미국 본장(정규장) 개장 시각 LOC — 당일 중복 접수 방지.

타깃 미국 거래일 = KST 당일 (``target_us_date_for_evening_loc``).
저녁(18:05 KST) 프리마켓 LOC 접수와 같은 미국 거래일 중복 방지.
- 계획(18:00): 알림만 — 스킵하지 않음
- LOC 접수(18:05): target US date에 체결 이력이 있으면 주문 생략
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from broker.toss_client import TossClient
    from cycles.cycle_tracker import CycleTracker

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")


def parse_when(raw: str) -> datetime.datetime | None:
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def us_session_date_from_when(raw: str) -> str | None:
    """체결·주문 시각 → 미국 동부 달력 날짜 (거래일)."""
    dt = parse_when(raw)
    if not dt:
        text = str(raw).strip()
        if len(text) >= 10 and text[4] == "-":
            return text[:10]
        return None
    return dt.astimezone(NY).date().isoformat()


def regular_open_kst_fallback(us_date: str) -> datetime.datetime:
    """하위 호환 — KST 고정 본장 개장 시각."""
    from strategy.market_schedule import regular_open_kst as _kst_open
    return _kst_open(us_date)


def order_submitted_before_regular_open(
    entry: dict, us_date: str, open_kst: datetime.datetime,
) -> bool:
    """KST us_date 당일, 본장 개장 시각 이전 주문 접수 여부."""
    ordered_raw = str(
        entry.get("ordered_at") or entry.get("submitted_at") or entry.get("at") or ""
    )
    ordered_dt = parse_when(ordered_raw)
    if not ordered_dt:
        return False
    kst = ordered_dt.astimezone(KST)
    if kst.date().isoformat() != us_date:
        return False
    return kst < open_kst


def has_loc_order_before_regular_open(
    st: dict,
    symbol: str,
    us_date: str,
    cycles: "CycleTracker",
    open_kst: datetime.datetime,
) -> bool:
    """fill_log·회차 trades·tracked_orders — 본장 전 LOC 접수 여부."""
    sym = symbol.upper()
    pools = list(st.get("fill_log") or []) + list(st.get("tracked_orders") or [])
    for entry in pools:
        if str(entry.get("symbol") or sym).upper() != sym:
            continue
        if order_submitted_before_regular_open(entry, us_date, open_kst):
            return True
    cur = cycles.get_symbol_data(sym).get("current") or {}
    for tr in cur.get("trades") or []:
        if order_submitted_before_regular_open(tr, us_date, open_kst):
            return True
    return False


def has_loc_order_before_regular_open_from_broker(
    broker: "TossClient",
    symbol: str,
    us_date: str,
    open_kst: datetime.datetime,
    *,
    days: int = 5,
) -> bool:
    """토스 체결 — state 미반영(앱 외 매매) 대비."""
    try:
        fills = broker.list_broker_fills(symbol, days=days, max_orders=40)
    except Exception:
        return False
    for fill in fills:
        if order_submitted_before_regular_open(fill, us_date, open_kst):
            return True
    return False


# 하위 호환 별칭 (executor/plan_formatter)
def has_us_session_fill_in_state(
    st: dict, symbol: str, us_date: str, cycles: "CycleTracker", open_kst: datetime.datetime,
) -> bool:
    return has_loc_order_before_regular_open(st, symbol, us_date, cycles, open_kst)


def has_us_session_fill_from_broker(
    broker: "TossClient",
    symbol: str,
    us_date: str,
    open_kst: datetime.datetime,
    *,
    days: int = 5,
) -> bool:
    return has_loc_order_before_regular_open_from_broker(
        broker, symbol, us_date, open_kst, days=days,
    )
