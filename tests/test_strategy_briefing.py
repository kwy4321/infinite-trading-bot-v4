"""아침 브리핑 무매 현황 — 직전 종가 LOC 체결 한 줄."""

from __future__ import annotations

import re

from briefing.strategy_briefing import format_strategy_briefing
from tests.conftest import FakeApp, FakeCycles, FakeState


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def test_session_trades_one_line_buy():
    app = FakeApp(dry=True, active=("TQQQ",))
    app.state = FakeState({"TQQQ": {"fill_log": []}})
    cycles = FakeCycles()
    cycles.symbol_data["current"]["trades"] = [
        {
            "side": "BUY",
            "qty": 2,
            "price": 55.0,
            "t_before": 0.0,
            "t_after": 0.5,
            "filled_at": "2026-03-12T05:30:00+09:00",
        },
    ]
    app.cycles = cycles
    text = _plain(format_strategy_briefing(app, "2026-03-11", session_label="3/11(수)"))
    assert "직전 종가 LOC · 3/11(수)" in text
    assert "매수 2주 @ $55.00" in text
    assert "T 0.0→0.5" in text or "T 0→0.5" in text


def test_session_trades_one_line_no_fill():
    app = FakeApp(dry=True, active=("TQQQ",))
    text = _plain(format_strategy_briefing(app, "2026-03-11", session_label="3/11(수)"))
    assert "직전 종가 LOC · 3/11(수)" in text
    assert "체결 없음" in text


def test_session_trades_one_line_buy_and_sell():
    app = FakeApp(dry=True, active=("SOXL",))
    app.state = FakeState({"SOXL": {"fill_log": []}})
    cycles = FakeCycles()
    cycles.symbol_data["current"]["trades"] = [
        {
            "side": "BUY",
            "qty": 3,
            "price": 28.5,
            "t_before": 1.0,
            "t_after": 1.25,
            "filled_at": "2026-03-12T05:28:00+09:00",
        },
        {
            "side": "SELL",
            "qty": 5,
            "price": 30.2,
            "avg_before": 28.0,
            "t_before": 1.25,
            "t_after": 1.0,
            "filled_at": "2026-03-12T05:31:00+09:00",
        },
    ]
    app.cycles = cycles
    text = _plain(format_strategy_briefing(app, "2026-03-11", session_label="3/11(수)"))
    assert "매수 3주 @ $28.50" in text
    assert "매도 5주 @ $30.20" in text
    assert "손익" in text
    assert "+$11.00" in text
    assert "▲ +$11.00" not in text


def test_sell_realized_pnl_from_avg_before():
    from core.trade_pnl import sell_realized_pnl

    pnl = sell_realized_pnl({
        "side": "SELL", "qty": 5, "price": 30.2, "avg_before": 28.0,
    })
    assert pnl == (11.0, 7.86)
