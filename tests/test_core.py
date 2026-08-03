"""core 계층 단위 테스트 — 금액 파싱·시간·종목."""

from __future__ import annotations

import datetime

import pytest

from core.clock import (
    KST,
    LOC_SUBMIT_HHMM,
    loc_auto_submit_kst,
    ny_date_str,
    parse_iso,
    us_session_date,
)
from core.money import (
    cash_krw,
    cash_usd,
    holding_avg_price,
    holding_market_value,
    holding_unrealized,
    parse_money,
    parse_pct,
)
from core.symbols import SYMBOL_UNIVERSE, is_known, normalize_symbol, normalize_symbols


def test_parse_money_handles_every_toss_shape():
    assert parse_money(None) == 0.0
    assert parse_money(12) == 12.0
    assert parse_money("12.5") == 12.5
    assert parse_money("nope") == 0.0
    assert parse_money({"usd": "3.5", "krw": "4600"}) == 3.5
    assert parse_money({"usd": "3.5", "krw": "4600"}, "krw") == 4600.0
    assert parse_money({"us": "7"}) == 7.0
    assert parse_money({"total": {"usd": "9"}}) == 9.0
    assert parse_money({}) == 0.0


def test_parse_money_falls_back_to_krw_when_usd_missing():
    assert parse_money({"krw": "1000"}) == 1000.0


def test_parse_pct_converts_rate_to_percent():
    assert parse_pct({"rate": "0.05"}) == pytest.approx(5.0)
    assert parse_pct(0.1) == pytest.approx(10.0)
    assert parse_pct(None) is None
    assert parse_pct({}) is None


def test_cash_helpers_read_buying_power():
    assert cash_usd(None) == 0.0
    assert cash_usd({"cashBuyingPower": {"usd": "100"}}) == 100.0
    assert cash_krw({"cashBuyingPower": {"krw": "5000"}}) == 5000.0
    assert cash_usd({"cash": "42"}) == 42.0


def test_holding_helpers():
    item = {
        "symbol": "TQQQ",
        "quantity": "10",
        "averagePurchasePrice": "50",
        "lastPrice": "60",
    }
    assert holding_avg_price(item) == 50.0
    assert holding_market_value(item) == 600.0
    usd, pct = holding_unrealized(item)
    assert usd == 100.0
    assert pct == 20.0


def test_holding_avg_price_uses_cost_fallback():
    assert holding_avg_price({"cost": {"averagePrice": "33"}}) == 33.0


def test_normalize_symbols_filters_to_universe():
    assert normalize_symbols(["tqqq", "SOXL", "AAPL", "tqqq"]) == ["TQQQ", "SOXL"]
    assert normalize_symbols("tqqq, soxl") == ["TQQQ", "SOXL"]
    assert normalize_symbols(None) == []
    assert normalize_symbol(" soxl ") == "SOXL"
    assert is_known("TQQQ") and not is_known("AAPL")
    assert "TQQQ" in SYMBOL_UNIVERSE


def test_loc_auto_submit_is_kst_1805():
    when = loc_auto_submit_kst("2026-08-03")
    assert (when.hour, when.minute) == LOC_SUBMIT_HHMM
    assert when.tzinfo is KST
    assert when.date() == datetime.date(2026, 8, 3)


def test_us_session_date_uses_new_york():
    # KST 2026-08-04 07:00 == NY 2026-08-03 18:00
    assert us_session_date("2026-08-04T07:00:00+09:00") == "2026-08-03"
    assert us_session_date("") == ""
    assert us_session_date("garbage") == ""


def test_parse_iso_accepts_z_suffix():
    parsed = parse_iso("2026-08-03T12:00:00Z")
    assert parsed is not None and parsed.utcoffset() == datetime.timedelta(0)


def test_ny_date_str_is_iso():
    value = ny_date_str(datetime.datetime(2026, 8, 4, 7, 0, tzinfo=KST))
    assert value == "2026-08-03"
