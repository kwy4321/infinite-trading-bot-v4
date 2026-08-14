"""장부 export — 토스 재조회를 기본 생략하는지."""

from __future__ import annotations

import datetime

from reporting.dashboard_data import broker_lookback_days, prepare_ledger_for_export


def test_lookback_uses_cycle_start_not_a_full_year():
    started = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    days = broker_lookback_days({"current": {"started_at": started}})
    assert days == 30  # 최소 30일


def test_lookback_missing_start_is_short():
    assert broker_lookback_days({"current": {}}) == 30
    assert broker_lookback_days({}) == 30


def test_prepare_ledger_skips_toss_by_default(fake_app):
    fake_app._dry = False
    fake_app.broker.fills_calls = []

    prepare_ledger_for_export(fake_app)

    assert fake_app.broker.fills_calls == []


def test_prepare_ledger_rebuild_does_not_pass_extra_order_ids(fake_app):
    fake_app._dry = False
    fake_app.broker.fills_calls = []

    prepare_ledger_for_export(fake_app, rebuild_broker=True)

    assert fake_app.broker.fills_calls
    for call in fake_app.broker.fills_calls:
        assert "extra_order_ids" not in call or not call.get("extra_order_ids")
        assert call["max_orders"] == 100
