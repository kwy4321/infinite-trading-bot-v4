"""services 계층 — 현재가·가용잔금·계좌 스냅샷."""

from __future__ import annotations

from services.account_service import fetch_account_snapshot
from services.market_data import resolve_price, resolve_prices
from services.trading_context import (
    dry_mode_reason,
    is_dry,
    resolve_available_cash,
    sync_broker_dry_run,
)


def test_is_dry_reads_settings(fake_app):
    assert is_dry(fake_app) is True
    assert dry_mode_reason(fake_app) == "토스 API 키 미설정"


def test_dry_mode_reason_is_empty_when_live(fake_app):
    fake_app._dry = False
    assert is_dry(fake_app) is False
    assert dry_mode_reason(fake_app) == ""


def test_sync_broker_dry_run_matches_settings(fake_app):
    fake_app.broker.dry_run = False
    sync_broker_dry_run(fake_app)
    assert fake_app.broker.dry_run is True


def test_resolve_available_cash_is_principal_minus_buy_plus_sell(fake_app):
    # principal 10000 − 매수 500 + 매도 100
    assert resolve_available_cash(fake_app, "TQQQ") == 9600.0


def test_resolve_prices_in_dry_mode_uses_state_avg(fake_app):
    prices = resolve_prices(fake_app, ["TQQQ"])
    assert prices == {"TQQQ": 50.0}


def test_resolve_prices_live_uses_holdings(fake_app):
    fake_app._dry = False
    prices = resolve_prices(fake_app, ["tqqq"])
    assert prices["TQQQ"] == 60.0  # marketValue 600 / 10주


def test_resolve_prices_unknown_symbol_falls_back_to_state(fake_app):
    fake_app._dry = False
    prices = resolve_prices(fake_app, ["SOXL"])
    assert prices["SOXL"] == 50.0


def test_resolve_prices_never_raises_on_broker_error(fake_app):
    fake_app._dry = False

    def boom():
        raise RuntimeError("toss down")

    fake_app.broker.get_holdings_overview = boom
    assert resolve_prices(fake_app, ["TQQQ"]) == {"TQQQ": 50.0}


def test_resolve_prices_empty_input(fake_app):
    assert resolve_prices(fake_app, []) == {}


def test_resolve_price_single(fake_app):
    assert resolve_price(fake_app, "TQQQ") == 50.0


def test_account_snapshot_is_empty_in_dry(fake_app):
    snap = fetch_account_snapshot(fake_app)
    assert snap.dry is True
    assert snap.total_usd == 0.0


def test_account_snapshot_aggregates_live(fake_app):
    fake_app._dry = False
    snap = fetch_account_snapshot(fake_app)
    assert snap.ok and not snap.dry
    assert snap.cash_usd == 600.0
    assert snap.cash_krw == 800000.0
    assert snap.stock_usd == 600.0
    assert snap.stock_krw == 800000.0
    assert snap.total_usd == 1200.0
    assert snap.total_krw == 2410000.0
    assert snap.fx_rate == 1350.0
    assert snap.unrealized_usd == 100.0
    assert snap.unrealized_pct == 20.0
    assert [h.symbol for h in snap.holdings] == ["TQQQ"]
    assert snap.holdings[0].last_price == 60.0
    assert snap.holdings[0].market_value_usd == 600.0


def test_account_snapshot_survives_broker_failure(fake_app):
    fake_app._dry = False

    def boom(*_args, **_kwargs):
        raise RuntimeError("toss down")

    fake_app.broker.get_buying_power = boom
    snap = fetch_account_snapshot(fake_app)
    assert snap.ok is False


def test_tracked_filters_to_active_symbols(fake_app):
    fake_app._dry = False
    snap = fetch_account_snapshot(fake_app)
    assert [h.symbol for h in snap.tracked(["TQQQ"])] == ["TQQQ"]
    # 매칭이 없으면 전체를 그대로 — 총자산이 0으로 보이는 사고 방지
    assert [h.symbol for h in snap.tracked(["SOXL"])] == ["TQQQ"]
