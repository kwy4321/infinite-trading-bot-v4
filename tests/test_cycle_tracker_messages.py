"""회차 메시지 — HTML 유효성과 T 표기 규칙."""

from __future__ import annotations

from cycles.cycle_tracker import CycleTracker
from render.html import validate_html
from render.numbers import t_transition


def test_t_transition_rules():
    assert t_transition(12, 13) == "T 12→13"
    assert t_transition(13, 13) == "T 13"
    assert t_transition(None, 13) == "T 13"
    assert t_transition(12, None) == "T 12"
    assert t_transition(None, None) == "T —"
    assert t_transition("", "") == "T —"
    assert t_transition("bad", None) == "T —"


def test_format_trade_line_is_valid_html():
    trade = {
        "side": "BUY",
        "symbol": "TQQQ",
        "qty": 3,
        "price": 55.5,
        "ordered_at": "2026-08-03T09:30:00+09:00",
        "t_before": 12,
        "t_after": 13,
    }
    line = CycleTracker.format_trade_line("TQQQ", trade, index=1)
    assert validate_html(line) == []
    assert "T 12→13" in line
    assert "TQQQ" in line


def test_format_trade_line_single_share_omits_total():
    trade = {"side": "SELL", "qty": 1, "price": 60.0, "at": "2026-08-03"}
    line = CycleTracker.format_trade_line("TQQQ", trade)
    assert "합" not in line
    assert validate_html(line) == []


def test_graduation_message_has_single_blockquote(tmp_path):
    tracker = CycleTracker(str(tmp_path))
    completed = {
        "cycle_no": 3,
        "started_at": "2026-07-01",
        "ended_at": "2026-08-01",
        "profit_usd": 250.0,
        "profit_pct": 12.5,
        "buy_count": 5,
        "sell_count": 2,
    }
    msg = tracker.format_graduation_message(completed, "TQQQ")
    assert msg.count("<blockquote>") == 1
    assert validate_html(msg) == []


def test_graduation_message_escapes_note(tmp_path):
    tracker = CycleTracker(str(tmp_path))
    completed = {
        "cycle_no": 1,
        "started_at": "2026-07-01",
        "ended_at": "2026-08-01",
        "profit_usd": -10.0,
        "profit_pct": -1.0,
        "buy_count": 1,
        "sell_count": 1,
        "note": "<b>주의</b> & 확인",
    }
    msg = tracker.format_graduation_message(completed, "TQQQ")
    assert "&lt;b&gt;" in msg
    assert validate_html(msg) == []


def test_available_cash_matches_ledger(tmp_path):
    tracker = CycleTracker(str(tmp_path))
    tracker.ensure_current("TQQQ", 10000.0)
    assert tracker.available_cash("TQQQ", 10000.0) == 10000.0


def test_monthly_report_is_valid_html(tmp_path):
    tracker = CycleTracker(str(tmp_path))
    msg = tracker.format_monthly_report(2026, "TQQQ")
    assert validate_html(msg) == []
