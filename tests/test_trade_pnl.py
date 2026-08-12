"""매도 실현손익 — 계산·브리핑·매매내역 일치."""

from __future__ import annotations

import re

import pytest

from briefing.strategy_briefing import format_strategy_briefing
from core.trade_pnl import sell_profit_fields, sell_realized_pnl
from cycles.cycle_tracker import CycleTracker
from render.numbers import realized_pnl_brief
from strategy.fill_processor import FillProcessor
from tests.conftest import FakeApp, FakeCycles, FakeState


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def test_sell_realized_pnl_matches_stored_fields():
    tr = {
        "side": "SELL", "qty": 5, "price": 30.2,
        "avg_before": 28.0,
        **sell_profit_fields(price=30.2, qty=5, avg_before=28.0),
    }
    assert sell_realized_pnl(tr) == (11.0, 7.86)


def test_briefing_and_trade_line_show_same_pnl():
    trade = {
        "side": "SELL",
        "qty": 5,
        "price": 30.2,
        "avg_before": 28.0,
        "filled_at": "2026-03-12T05:31:00+09:00",
        "t_before": 1.25,
        "t_after": 1.0,
        **sell_profit_fields(price=30.2, qty=5, avg_before=28.0),
    }
    pnl = sell_realized_pnl(trade)
    assert pnl is not None
    pnl_text = _plain(realized_pnl_brief(pnl[0], pnl[1]))
    history_line = _plain(CycleTracker.format_trade_line("SOXL", trade))
    assert pnl_text in history_line

    app = FakeApp(dry=True, active=("SOXL",))
    app.state = FakeState({"SOXL": {"fill_log": []}})
    cycles = FakeCycles()
    cycles.symbol_data["current"]["trades"] = [trade]
    app.cycles = cycles
    briefing = _plain(format_strategy_briefing(app, "2026-03-11", session_label="3/11(수)"))
    assert "손익" in briefing
    assert "+$11.00" in briefing
    assert "▲ +$11.00" not in briefing


def test_fill_processor_matches_trade_line_pnl(tmp_path):
    """봇 체결 → record_trade → 매매내역 손익 = core/trade_pnl 계산."""
    cycles = CycleTracker(data_dir=tmp_path)
    processor = FillProcessor()
    state = {
        "T": 1.0,
        "qty": 10,
        "avg_price": 28.0,
        "principal": 10000.0,
        "split_count": 40,
    }
    cycles.ensure_current("SOXL", state["principal"])
    processor.apply_sell_fill(
        state,
        {"qty": 5, "price": 30.2, "action": "TAKE_PROFIT", "desc": "익절"},
        cycles,
        "SOXL",
    )
    trade = cycles.get_symbol_data("SOXL")["current"]["trades"][-1]
    assert trade.get("profit_usd") == 11.0
    line = _plain(CycleTracker.format_trade_line("SOXL", trade))
    assert "손익" in line
    assert "+$11.00" in line
    assert sell_realized_pnl(trade) == (11.0, 7.86)


def test_cycle_total_profit_equals_sum_of_sell_pnls(tmp_path):
    """회차 완료 profit_usd = 매도 건별 profit_usd 합."""
    cycles = CycleTracker(data_dir=tmp_path)
    processor = FillProcessor()
    state = {
        "T": 0.0,
        "qty": 0,
        "avg_price": 0.0,
        "principal": 10000.0,
        "split_count": 40,
    }
    cycles.ensure_current("TQQQ", state["principal"])
    processor.apply_buy_fill(
        state,
        {"qty": 10, "price": 50.0, "action": "BUY_FULL"},
        cycles,
        "TQQQ",
    )
    processor.apply_sell_fill(
        state,
        {"qty": 4, "price": 60.0, "action": "SELL_QUARTER"},
        cycles,
        "TQQQ",
    )
    processor.apply_sell_fill(
        state,
        {"qty": 6, "price": 55.0, "action": "TAKE_PROFIT"},
        cycles,
        "TQQQ",
    )
    completed = cycles.get_symbol_data("TQQQ")["completed"][-1]
    trades = completed["trades"]
    sell_pnls = [
        sell_realized_pnl(tr)[0]
        for tr in trades
        if tr.get("side") == "SELL" and sell_realized_pnl(tr)
    ]
    assert completed["profit_usd"] == pytest.approx(sum(sell_pnls), abs=0.01)
