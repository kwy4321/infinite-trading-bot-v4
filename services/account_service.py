"""계좌 스냅샷 — /balance · /dashboard · Streamlit 이 공유하는 단일 조회 경로.

이전에는 balance_formatter / records_dashboard_formatter / dashboard_data 가
각자 holdings·buyingPower·환율을 조합해서, 한쪽만 고치면 숫자가 어긋났다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.money import (
    cash_krw,
    cash_usd,
    holding_avg_price,
    holding_market_value,
    holding_unrealized,
    parse_money,
)
from core.symbols import normalize_symbol
from services.trading_context import is_dry

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Holding:
    symbol: str
    qty: float
    avg_price: float
    last_price: float
    market_value_usd: float
    market_value_krw: float
    unrealized_usd: float
    unrealized_pct: float | None

    @property
    def cost_usd(self) -> float:
        return round(self.qty * self.avg_price, 2)


@dataclass(frozen=True)
class AccountSnapshot:
    """계좌 1회 조회 결과. dry=True 면 브로커를 조회하지 않은 빈 스냅샷."""

    dry: bool = False
    ok: bool = True
    cash_usd: float = 0.0
    cash_krw: float = 0.0
    stock_usd: float = 0.0
    stock_krw: float = 0.0
    total_usd: float = 0.0
    total_krw: float = 0.0
    cost_usd: float = 0.0
    unrealized_usd: float = 0.0
    unrealized_pct: float | None = None
    fx_rate: float = 0.0
    holdings: tuple[Holding, ...] = field(default_factory=tuple)

    def tracked(self, symbols) -> tuple[Holding, ...]:
        """거래 중인 종목만. 매칭이 없으면 전체를 그대로 돌려준다."""
        wanted = {normalize_symbol(s) for s in (symbols or []) if s}
        if not wanted:
            return self.holdings
        picked = tuple(h for h in self.holdings if h.symbol in wanted)
        return picked or self.holdings

    def total_krw_or_converted(self) -> float:
        if self.total_krw > 0:
            return self.total_krw
        return self.total_usd * self.fx_rate if self.fx_rate > 0 else 0.0

    def as_dict(self) -> dict:
        """하위 호환 — 기존 포맷터가 쓰던 dict 형태."""
        return {
            "cash_usd": self.cash_usd,
            "total_usd": self.total_usd,
            "total_krw": self.total_krw,
            "unreal_usd": round(self.unrealized_usd, 2),
            "unreal_pct": self.unrealized_pct,
            "fx_rate": self.fx_rate,
        }


def _holding(item: dict) -> Holding:
    unreal_usd, unreal_pct = holding_unrealized(item)
    return Holding(
        symbol=normalize_symbol(item.get("symbol")) or "?",
        qty=parse_money(item.get("quantity")),
        avg_price=holding_avg_price(item),
        last_price=parse_money(item.get("lastPrice"), "usd"),
        market_value_usd=holding_market_value(item, "usd"),
        market_value_krw=holding_market_value(item, "krw"),
        unrealized_usd=unreal_usd,
        unrealized_pct=unreal_pct,
    )


def _fx_rate(app: App) -> float:
    try:
        fx = app.broker.get_exchange_rate("USD", "KRW") or {}
    except Exception:
        logger.debug("exchange rate lookup failed", exc_info=True)
        return 0.0
    return float(fx.get("rate") or fx.get("midRate") or 0)


def fetch_account_snapshot(app: App) -> AccountSnapshot:
    """브로커 계좌 1회 조회. 실패해도 예외 없이 ok=False 스냅샷을 돌려준다."""
    if is_dry(app):
        return AccountSnapshot(dry=True)
    try:
        broker = app.broker
        cash_usd_val = cash_usd(broker.get_buying_power("USD"))
        cash_krw_val = cash_krw(broker.get_buying_power("KRW"))

        overview = broker.get_holdings_overview() or {}
        holdings = tuple(_holding(i) for i in overview.get("items", []))

        stock_usd = sum(h.market_value_usd for h in holdings)
        stock_krw = sum(h.market_value_krw for h in holdings)
        cost_usd = sum(h.cost_usd for h in holdings)
        unreal_usd = sum(h.unrealized_usd for h in holdings)

        total_usd = parse_money(overview.get("totalEvaluationAmount"), "usd")
        total_krw = parse_money(overview.get("totalEvaluationAmount"), "krw")
        if total_usd <= 0:
            total_usd = cash_usd_val + stock_usd
        if total_krw <= 0 and cash_krw_val > 0:
            total_krw = cash_krw_val + stock_krw

        fx = _fx_rate(app)
        if total_krw <= 0 and fx > 0 and total_usd > 0:
            total_krw = total_usd * fx

        return AccountSnapshot(
            cash_usd=cash_usd_val,
            cash_krw=cash_krw_val,
            stock_usd=stock_usd,
            stock_krw=stock_krw,
            total_usd=total_usd,
            total_krw=total_krw,
            cost_usd=cost_usd,
            unrealized_usd=round(unreal_usd, 2),
            unrealized_pct=(
                round(unreal_usd / cost_usd * 100, 2) if cost_usd > 0 else None
            ),
            fx_rate=fx,
            holdings=holdings,
        )
    except Exception:
        logger.warning("account snapshot failed", exc_info=True)
        return AccountSnapshot(ok=False)
