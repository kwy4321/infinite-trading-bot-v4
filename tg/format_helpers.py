"""Shared helpers for Telegram formatters."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from broker.toss_client import _money

from config.settings import is_dry_mode

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)


def is_dry(app: App) -> bool:
    return is_dry_mode(app.settings, force_live=app.runtime.force_live())


def dry_mode_reason(app: App) -> str:
    """DRY일 때 원인 한 줄."""
    if is_dry_mode(app.settings, force_live=app.runtime.force_live()):
        if not app.settings.has_toss:
            return "토스 API 키 미설정"
        if app.settings.dry_run:
            return ".env DRY_RUN=true (설정→실거래 켜기)"
        return "알 수 없음"
    return ""


def sync_broker_dry_run(app: App) -> None:
    app.broker.dry_run = is_dry(app)


def resolve_available_cash(app: App, symbol: str, st: dict | None = None) -> float:
    """리버스 쿼터매수용 가용 잔금 ≈ 원금 − 매수 + 매도 (회차 기준)."""
    if st is None:
        st = app.state.load(symbol)
    principal = float(st.get("principal", 0.0))
    sym_data = app.cycles.get_symbol_data(symbol.upper())
    cur = sym_data.get("current") or {}
    buy = float(cur.get("total_buy_usd", 0.0))
    sell = float(cur.get("total_sell_usd", 0.0))
    return max(0.0, round(principal - buy + sell, 2))


def resolve_price(app: App, symbol: str) -> float:
    """Best-effort market price; returns 0.0 on failure or DRY_RUN."""
    return resolve_prices(app, [symbol]).get(symbol.upper(), 0.0)


def _resolve_prices_fallback(app: App, symbols: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for sym in symbols:
        st = app.state.load(sym.upper())
        out[sym.upper()] = float(st.get("avg_price") or 0)
    return out


def resolve_prices(app: App, symbols: list[str]) -> dict[str, float]:
    """종목별 현재가 — holdings 1회 조회 (주문계획·현황 공통)."""
    out: dict[str, float] = {}
    want = [s.upper() for s in symbols if s]
    if not want:
        return out
    if is_dry(app):
        return _resolve_prices_fallback(app, want)
    try:
        overview = app.broker.get_holdings_overview() or {}
        items = {str(i.get("symbol", "")).upper(): i for i in overview.get("items", [])}
        for sym in want:
            item = items.get(sym)
            if not item:
                out[sym] = 0.0
                continue
            qty = int(float(item.get("quantity", 0) or 0))
            mkt = _money(item.get("marketValue"), "usd")
            if mkt <= 0:
                mkt = float(item.get("lastPrice", 0) or 0) * qty
            if qty > 0 and mkt > 0:
                out[sym] = mkt / qty
            else:
                out[sym] = float(item.get("lastPrice", 0) or 0)
        missing = [s for s in want if out.get(s, 0) <= 0]
        for sym in missing[:2]:
            try:
                px = float(app.broker.get_price(sym) or 0)
                if px > 0:
                    out[sym] = px
            except Exception:
                logger.debug("get_price failed %s", sym, exc_info=True)
        for sym in want:
            if out.get(sym, 0) <= 0:
                st = app.state.load(sym)
                out[sym] = float(st.get("avg_price") or 0)
    except Exception:
        logger.warning("resolve_prices failed — state fallback", exc_info=True)
        return _resolve_prices_fallback(app, want)
    return out
