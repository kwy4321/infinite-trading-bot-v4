"""미국 지수 요약 — 나스닥 종합(^IXIC) + 필라델피아 반도체(^SOX).

Yahoo Finance 일봉으로 **지정 거래일** 종가 대비 전일 종가만 계산한다.
휴장일에는 당일 등락을 표시하지 않는다.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import requests

from briefing.market_context import get_briefing_market_context
from tg.ui import code, dim, pct, quote, section, trend_arrow

if TYPE_CHECKING:
    from broker.toss_client import TossClient

logger = logging.getLogger(__name__)

_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (infinite-trading-bot briefing)"}
_INDICES = (
    ("^IXIC", "나스닥 종합"),
    ("^SOX", "필라델피아 반도체"),
)
_NY = ZoneInfo("America/New_York")


def _daily_closes(symbol: str) -> dict[str, float]:
    """symbol → {YYYY-MM-DD: close}."""
    resp = requests.get(
        _YAHOO.format(symbol=symbol),
        params={"range": "1mo", "interval": "1d"},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    closes = (result.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
    out: dict[str, float] = {}
    for ts, raw in zip(timestamps, closes):
        if raw is None:
            continue
        day = datetime.datetime.fromtimestamp(int(ts), tz=_NY).date().isoformat()
        out[day] = float(raw)
    return out


def _last_two_closes(by_date: dict[str, float], on_or_before: str) -> tuple[str, str] | None:
    dates = sorted(d for d in by_date if d <= on_or_before)
    if len(dates) < 2:
        return None
    return dates[-1], dates[-2]


def _fetch_one(symbol: str, session_date: str) -> dict | None:
    try:
        by_date = _daily_closes(symbol)
        pair = _last_two_closes(by_date, session_date)
        if not pair:
            logger.warning("지수 일봉 부족 %s session<=%s", symbol, session_date)
            return None
        last_day, prev_day = pair
        price = by_date[last_day]
        prev = by_date[prev_day]
        change = price - prev
        change_pct = (change / prev * 100.0) if prev else 0.0
        return {
            "price": price,
            "change": change,
            "pct": change_pct,
            "session_label": _fmt_label(last_day),
            "prev_label": _fmt_label(prev_day),
        }
    except Exception as exc:
        logger.warning("지수 조회 실패 %s: %s", symbol, exc)
        return None


def _fmt_label(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso[:10])
        wd = ("월", "화", "수", "목", "금", "토", "일")[d.weekday()]
        return f"{d.month}/{d.day}({wd})"
    except ValueError:
        return iso[:10]


def _build_sync(broker: "TossClient | None") -> str:
    ctx = get_briefing_market_context(broker)
    session_date = ctx["session_date"]
    session_label = ctx["session_label"]

    if ctx["us_holiday"]:
        header = section("미국 증시", "🇺🇸")
        holiday = ctx["holiday_label"] or "—"
        note = (
            f"<b>{holiday}</b> 미국 정규장 <b>휴장</b>\n"
            f"{dim(f'아래는 직전 마감일 {session_label} 종가 기준입니다.')}"
        )
    else:
        header = section(f"미국 증시 마감 · {session_label}", "🇺🇸")
        note = dim(f"직전 마감일 {session_label} · 전 거래일 대비")

    rows = [note, ""]
    for symbol, name in _INDICES:
        data = _fetch_one(symbol, session_date)
        if data is None:
            rows.append(f"{dim(name)}  {dim('데이터 없음')}")
            continue
        up = data["change"] >= 0
        sign = "+" if up else ""
        price_str = f"{data['price']:,.2f}"
        change_str = f"{sign}{data['change']:,.2f}"
        sub = dim(f" ({data['prev_label']}→{data['session_label']})")
        rows.append(
            f"{trend_arrow(up)} {dim(name)}{sub}  {code(price_str)}  "
            f"{code(change_str)} {pct(data['pct'])}"
        )
    return f"{header}\n{quote(*rows)}"


async def fetch_index_summary(broker: "TossClient | None" = None) -> str:
    return await asyncio.to_thread(_build_sync, broker)
