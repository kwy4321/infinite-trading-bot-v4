"""미국 정규장 거래일(ET) 기준 — 당일 이미 체결됐는지 판별.

저녁(18:05 KST) 프리마켓 LOC 접수와 같은 미국 거래일 중복 방지.
- 계획: 알림만 — 스킵하지 않음
- LOC 접수: target US date에 체결 이력이 있으면 주문 생략
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from broker.toss_client import TossClient
    from cycles.cycle_tracker import CycleTracker

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


def _fill_matches_us_date(entry: dict, us_date: str) -> bool:
    if int(entry.get("qty") or 0) <= 0:
        return False
    when = entry.get("ordered_at") or entry.get("filled_at") or entry.get("at") or ""
    return us_session_date_from_when(when) == us_date


def has_us_session_fill_in_state(st: dict, symbol: str, us_date: str, cycles: "CycleTracker") -> bool:
    """fill_log·회차 trades에 해당 미국 거래일 체결이 있는지."""
    sym = symbol.upper()
    for entry in st.get("fill_log") or []:
        if str(entry.get("symbol") or sym).upper() != sym:
            continue
        if _fill_matches_us_date(entry, us_date):
            return True
    cur = cycles.get_symbol_data(sym).get("current") or {}
    for tr in cur.get("trades") or []:
        if _fill_matches_us_date(tr, us_date):
            return True
    return False


def has_us_session_fill_from_broker(
    broker: "TossClient", symbol: str, us_date: str, *, days: int = 5,
) -> bool:
    """토스 CLOSED 체결 — state 미반영(앱 직접 매매) 대비."""
    try:
        fills = broker.list_broker_fills(symbol, days=days, max_orders=40)
    except Exception:
        return False
    for fill in fills:
        if _fill_matches_us_date(fill, us_date):
            return True
    return False
