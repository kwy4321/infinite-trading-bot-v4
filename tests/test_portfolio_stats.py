"""portfolio_stats — 실현손익 집계."""

from __future__ import annotations

from cycles.cycle_tracker import CycleTracker


def test_portfolio_stats_includes_partial_sell_loss_in_current_cycle(tmp_path):
    tracker = CycleTracker(str(tmp_path))
    tracker.ensure_current("TQQQ", 10000.0)
    tracker.record_trade(
        "TQQQ",
        side="BUY", qty=10, price=50.0, action="BUY",
        t_before=0.0, t_after=1.0, avg_after=50.0, qty_after=10, source="test",
    )
    tracker.record_trade(
        "TQQQ",
        side="SELL", qty=5, price=45.0, action="SELL",
        t_before=1.0, t_after=0.5, avg_after=50.0, qty_after=5, source="test",
        avg_before=50.0,
    )

    stats = tracker.portfolio_stats(["TQQQ"], {"TQQQ": 5})

    assert stats["realized_usd"] == -25.0
    assert stats["completed_cycles"] == 0
    assert stats["per_symbol"]["TQQQ"]["realized_usd"] == -25.0


def test_portfolio_stats_completed_plus_current_sell(tmp_path):
    tracker = CycleTracker(str(tmp_path))
    data = tracker._load_all()
    sym = tracker._get(data, "TQQQ")
    sym["completed"] = [{
        "cycle_no": 1,
        "profit_usd": 100.0,
        "total_buy_usd": 500.0,
        "total_sell_usd": 600.0,
    }]
    sym["current"] = {
        "cycle_no": 2,
        "started_at": "2026-03-01",
        "principal": 10000.0,
        "total_buy_usd": 200.0,
        "total_sell_usd": 90.0,
        "buy_count": 1,
        "sell_count": 1,
        "max_T": 1.0,
        "trades": [{
            "side": "SELL",
            "qty": 2,
            "price": 45.0,
            "avg_before": 50.0,
            "profit_usd": -10.0,
            "profit_pct": -10.0,
        }],
    }
    tracker._save_all(data)

    stats = tracker.portfolio_stats(["TQQQ"], {"TQQQ": 3})

    assert stats["realized_usd"] == 90.0
    assert stats["completed_cycles"] == 1
