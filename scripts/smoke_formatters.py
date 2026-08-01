"""Smoke test — formatter runtime errors (missing imports, NameError)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _mock_app(*, dry: bool = True, symbols: list[str] | None = None) -> MagicMock:
    symbols = symbols or ["TQQQ"]
    app = MagicMock()
    app.settings.dry_run = dry
    app.settings.has_toss = not dry
    app.runtime.active_symbols.return_value = symbols
    app.state.load.return_value = {
        "T": 1.5,
        "split_count": 40,
        "qty": 10,
        "avg_price": 42.0,
        "principal": 10000.0,
        "force_one": False,
        "take_profit_pct": 15.0,
    }
    app.cycles.cycle_progress.return_value = 2
    app.cycles.calc_unrealized_pnl.return_value = {
        "cycle_pnl_usd": 120.0,
        "cycle_pnl_pct": 2.1,
    }
    app.strategy.resolve_mode.return_value = MagicMock(value="NORMAL_EARLY")
    app.strategy.resolve_mode_from_state.return_value = MagicMock(value="NORMAL_EARLY")
    app.strategy.get_plan_from_state.return_value = {
        "mode": "NORMAL_EARLY",
        "star_pct": 12.0,
        "star_price": 47.0,
        "star_buy": 46.99,
        "take_profit_pct": 15.0,
        "current_price": 43.0,
        "avg_price": 42.0,
        "premium_pct": 10,
        "one_buy_amount": 250.0,
        "buy_orders": [],
        "sell_orders": [],
        "reverse_mode": False,
        "reverse_first_day": False,
    }
    app.runtime.force_live.return_value = False
    app.broker.dry_run = dry
    sym_data = {"current": {"total_buy_usd": 0.0, "total_sell_usd": 0.0}}
    app.cycles.get_symbol_data.return_value = sym_data
    return app


def main() -> None:
    from tg.balance_formatter import _holding_rows, format_balance
    from tg.keyboards import (
        premium_keyboard,
        setting_keyboard,
        split_count_keyboard,
        take_profit_keyboard,
        trading_symbols_keyboard,
    )
    from tg.status_formatter import format_status
    from tg.plan_formatter import format_plans

    plan = format_plans(_mock_app(), ["TQQQ"], 10)
    assert "주문계획" in plan or "오늘" in plan, plan[:200]

    rows = _holding_rows({
        "symbol": "TQQQ",
        "quantity": 10,
        "averagePurchasePrice": 42.0,
        "lastPrice": 43.5,
        "marketValue": {"usd": "435.0"},
    })
    assert rows, "holding rows empty"
    assert "수량" in rows[1], rows

    status = format_status(_mock_app())
    assert "무매 현황" in status, status[:200]
    assert "TQQQ" in status, status[:200]
    assert "🎯" in status, status[:200]

    app = _mock_app(dry=False)
    app.broker.get_buying_power.return_value = {"cashBuyingPower": {"usd": "1000"}}
    app.broker.get_holdings_overview.return_value = {
        "items": [{
            "symbol": "TQQQ",
            "quantity": 10,
            "averagePurchasePrice": 42.0,
            "lastPrice": 43.5,
            "marketValue": {"usd": "435.0"},
        }],
        "totalEvaluationAmount": {"usd": "1435.0"},
    }
    app.broker.get_exchange_rate.return_value = {"rate": 1350.0}
    balance = format_balance(app)
    assert "계좌현황" in balance, balance[:200]
    assert "TQQQ" in balance, balance[:200]
    assert "📊" in balance, balance[:200]

    setting_keyboard(force_one=False, dry=True)
    premium_keyboard()
    take_profit_keyboard()
    split_count_keyboard("TQQQ")
    trading_symbols_keyboard(["TQQQ"], "TQQQ")

    print("smoke_formatters OK")


if __name__ == "__main__":
    main()
