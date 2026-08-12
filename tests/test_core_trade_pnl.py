"""core/trade_pnl — 매도 실현손익 계산."""

from __future__ import annotations

import pytest

from core.trade_pnl import sell_avg_cost, sell_profit_fields, sell_realized_pnl


def test_sell_profit_fields():
    assert sell_profit_fields(price=30.2, qty=5, avg_before=28.0) == {
        "profit_usd": 11.0,
        "profit_pct": 7.86,
    }


def test_sell_realized_pnl_prefers_stored():
    tr = {"side": "SELL", "profit_usd": 5.5, "profit_pct": 2.0}
    assert sell_realized_pnl(tr) == (5.5, 2.0)


def test_sell_avg_cost_partial_sell_uses_avg_after():
    tr = {"side": "SELL", "qty": 3, "qty_after": 7, "avg_after": 28.0}
    assert sell_avg_cost(tr) == 28.0


def test_sell_realized_pnl_computes_from_avg_before():
    tr = {"side": "SELL", "qty": 2, "price": 55.0, "avg_before": 50.0}
    assert sell_realized_pnl(tr) == (10.0, 10.0)
