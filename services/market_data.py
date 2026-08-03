"""현재가 조회 — 브로커 호출 1회로 여러 종목을 채운다.

폴백 순서: holdings 평가금액/수량 → lastPrice → get_price → state 평단.
DRY 모드나 조회 실패에서도 절대 예외를 올리지 않는다 (/plan 무응답 방지).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.money import parse_money
from core.symbols import normalize_symbol
from services.trading_context import is_dry

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)

#: holdings 로 못 채운 종목에 대한 개별 get_price 호출 상한 (레이트리밋 보호)
_MAX_INDIVIDUAL_LOOKUPS = 2


def _state_prices(app: App, symbols: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for sym in symbols:
        try:
            st = app.state.load(sym)
            out[sym] = float(st.get("avg_price") or 0)
        except Exception:
            logger.debug("state price fallback failed %s", sym, exc_info=True)
            out[sym] = 0.0
    return out


def _price_from_holding(item: dict) -> float:
    qty = int(parse_money(item.get("quantity")))
    market = parse_money(item.get("marketValue"), "usd")
    last = parse_money(item.get("lastPrice"), "usd")
    if market <= 0 and qty > 0 and last > 0:
        market = last * qty
    if qty > 0 and market > 0:
        return market / qty
    return last


def resolve_prices(app: App, symbols: list[str]) -> dict[str, float]:
    """종목별 현재가 — holdings 1회 조회 (주문계획·현황 공통)."""
    want = [normalize_symbol(s) for s in symbols if s]
    want = [s for s in dict.fromkeys(want) if s]
    if not want:
        return {}
    if is_dry(app):
        return _state_prices(app, want)

    try:
        overview = app.broker.get_holdings_overview() or {}
        items = {
            normalize_symbol(i.get("symbol")): i for i in overview.get("items", [])
        }
        out = {sym: _price_from_holding(items[sym]) for sym in want if sym in items}
        out.update({sym: 0.0 for sym in want if sym not in out})

        missing = [s for s in want if out.get(s, 0) <= 0]
        for sym in missing[:_MAX_INDIVIDUAL_LOOKUPS]:
            try:
                px = float(app.broker.get_price(sym) or 0)
                if px > 0:
                    out[sym] = px
            except Exception:
                logger.debug("get_price failed %s", sym, exc_info=True)

        still_missing = [s for s in want if out.get(s, 0) <= 0]
        if still_missing:
            out.update(_state_prices(app, still_missing))
        return out
    except Exception:
        logger.warning("resolve_prices failed — state fallback", exc_info=True)
        return _state_prices(app, want)


def resolve_price(app: App, symbol: str) -> float:
    """단일 종목 현재가. 실패·DRY 면 state 평단, 그것도 없으면 0.0."""
    return resolve_prices(app, [symbol]).get(normalize_symbol(symbol), 0.0)
