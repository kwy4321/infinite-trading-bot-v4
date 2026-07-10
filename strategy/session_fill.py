"""저녁(18:05 KST) 프리마켓 LOC — 당일 중복 접수 방지.

타깃 미국 거래일 = KST 당일 (``target_us_date_for_evening_loc``).
스킵 조건 = 해당 KST일 **18시 이후** 접수·체결만 (새벽 sync 체결은 제외).

예) 7/10 아침 plan: 타깃 7/10. 7/9 18:05 접수→7/10 새벽 체결은 7/9 접수라 스킵 안 함.
   7/10 18:05 이후 접수·체결 있으면 7/10 저녁 LOC 스킵.
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
EVENING_LOC_KST_HOUR = 18


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


def _kst_on_target_evening(us_date: str, dt: datetime.datetime) -> bool:
    """KST 달력이 us_date(저녁 LOC 타깃일)이고 18시 이후인지."""
    kst = dt.astimezone(KST)
    return kst.date().isoformat() == us_date and kst.hour >= EVENING_LOC_KST_HOUR


def fill_blocks_evening_loc(entry: dict, us_date: str) -> bool:
    """저녁 LOC 자동접수 스킵 대상 체결인지 (당일 18시 이후 접수·체결만)."""
    if int(entry.get("qty") or 0) <= 0:
        return False

    ordered_raw = str(entry.get("ordered_at") or "")
    filled_raw = str(entry.get("filled_at") or entry.get("at") or "")

    ordered_dt = parse_when(ordered_raw)
    if ordered_dt and _kst_on_target_evening(us_date, ordered_dt):
        return True

    if ordered_raw:
        return False

    if not filled_raw or us_session_date_from_when(filled_raw) != us_date:
        return False
    filled_dt = parse_when(filled_raw)
    return bool(filled_dt and _kst_on_target_evening(us_date, filled_dt))


def has_us_session_fill_in_state(st: dict, symbol: str, us_date: str, cycles: "CycleTracker") -> bool:
    """fill_log·회차 trades — 저녁 LOC 스킵 대상 체결 여부."""
    sym = symbol.upper()
    for entry in st.get("fill_log") or []:
        if str(entry.get("symbol") or sym).upper() != sym:
            continue
        if fill_blocks_evening_loc(entry, us_date):
            return True
    cur = cycles.get_symbol_data(sym).get("current") or {}
    for tr in cur.get("trades") or []:
        if fill_blocks_evening_loc(tr, us_date):
            return True
    return False


def has_us_session_fill_from_broker(
    broker: "TossClient", symbol: str, us_date: str, *, days: int = 5,
) -> bool:
    """토스 CLOSED 체결 — state 미반영(앱 외 매매) 대비."""
    try:
        fills = broker.list_broker_fills(symbol, days=days, max_orders=40)
    except Exception:
        return False
    for fill in fills:
        if fill_blocks_evening_loc(fill, us_date):
            return True
    return False
