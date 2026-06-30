"""미국 지수 요약 — 나스닥 종합(^IXIC) + 필라델피아 반도체(^SOX).

Yahoo Finance 차트 API를 직접 호출한다(키 불필요). requests 는 블로킹이라
asyncio.to_thread 로 감싼다.
"""

import asyncio
import logging

import requests

from tg.ui import code, dim, pct, pnl_dot, quote, section

logger = logging.getLogger(__name__)

_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (infinite-trading-bot briefing)"}
_INDICES = (
    ("^IXIC", "나스닥 종합"),
    ("^SOX", "필라델피아 반도체"),
)


def _fetch_one(symbol: str) -> dict | None:
    try:
        resp = requests.get(
            _YAHOO.format(symbol=symbol),
            params={"range": "5d", "interval": "1d"},
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        prev = float(prev)
        change = price - prev
        change_pct = (change / prev * 100.0) if prev else 0.0
        return {"price": price, "change": change, "pct": change_pct}
    except Exception as exc:
        logger.warning("지수 조회 실패 %s: %s", symbol, exc)
        return None


def _build_sync() -> str:
    rows = []
    for symbol, name in _INDICES:
        data = _fetch_one(symbol)
        if data is None:
            rows.append(f"⚪ {dim(name)}  데이터 없음")
            continue
        up = data["change"] >= 0
        sign = "+" if up else ""
        price_str = f"{data['price']:,.2f}"
        change_str = f"{sign}{data['change']:,.2f}"
        rows.append(
            f"{pnl_dot(up)} {dim(name)}  {code(price_str)}  "
            f"{code(change_str)} {pct(data['pct'])}"
        )
    return f"{section('미국 증시 마감', '📈')}\n{quote(*rows)}"


async def fetch_index_summary() -> str:
    return await asyncio.to_thread(_build_sync)
