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
    return app


def main() -> None:
    from tg.balance_formatter import _holding_rows, format_balance
    from tg.status_formatter import format_status

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

    print("smoke_formatters OK")


if __name__ == "__main__":
    main()
