"""Shared helpers for Telegram formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from broker.toss_client import _money

if TYPE_CHECKING:
    from app import App


def is_dry(app: App) -> bool:
    if app.runtime.force_live() and app.settings.has_toss:
        return False
    return app.settings.dry_run or not app.settings.has_toss


def dry_mode_reason(app: App) -> str:
    """DRY일 때 원인 한 줄."""
    if app.runtime.force_live() and app.settings.has_toss:
        return ""
    if not app.settings.has_toss:
        return "토스 API 키 미설정"
    if app.settings.dry_run:
        return ".env DRY_RUN=true"
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


def resolve_prices(app: App, symbols: list[str]) -> dict[str, float]:
    """종목별 현재가 — holdings 1회 조회 후 캐시 (주문계획 등)."""
    out: dict[str, float] = {}
    want = [s.upper() for s in symbols]
    if is_dry(app):
        for sym in want:
            st = app.state.load(sym)
            out[sym] = float(st.get("avg_price") or 0)
        return out
    try:
        overview = app.broker.get_holdings_overview() or {}
        items = {str(i.get("symbol", "")).upper(): i for i in overview.get("items", [])}
        for sym in want:
            item = items.get(sym)
            if not item:
                out[sym] = float(app.broker.get_price(sym) or 0)
                continue
            qty = int(float(item.get("quantity", 0) or 0))
            cost = item.get("cost") or {}
            mkt = _money(item.get("marketValue"), "usd")
            if mkt <= 0:
                mkt = float(item.get("lastPrice", 0) or 0) * qty
            if qty > 0 and mkt > 0:
                out[sym] = mkt / qty
            else:
                out[sym] = float(app.broker.get_price(sym) or 0)
    except Exception:
        for sym in want:
            st = app.state.load(sym)
            out[sym] = float(st.get("avg_price") or 0)
    return out
