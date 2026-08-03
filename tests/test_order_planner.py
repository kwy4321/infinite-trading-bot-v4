"""LOC 접수 전 매도 수량 cap — MOC 중복·422 회귀 방지."""

from __future__ import annotations

from strategy.order_planner import prepare_loc_submit_orders, resolve_holdings_qty


def test_resolve_holdings_qty_live_uses_broker_when_lower():
    st = {"qty": 40}
    broker = {"qty": 30, "current_price": 10.0}
    assert resolve_holdings_qty(st, broker, dry=False) == 30


def test_resolve_holdings_qty_live_uses_state_when_broker_higher():
    st = {"qty": 40}
    broker = {"qty": 50, "current_price": 10.0}
    assert resolve_holdings_qty(st, broker, dry=False) == 40


def test_resolve_holdings_qty_dry_ignores_broker():
    st = {"qty": 40}
    broker = {"qty": 30}
    assert resolve_holdings_qty(st, broker, dry=True) == 40


def test_prepare_loc_submit_orders_no_duplicate_moc():
    """MOC 가 LOC cap 목록과 별도로 한 번 더 붙지 않아야 한다."""
    filtered = {
        "buy_orders": [],
        "sell_orders": [
            {"side": "SELL", "qty": 10, "exec": "MOC", "price": 0},
            {"side": "SELL", "qty": 10, "exec": "LOC", "price": 50.0},
            {"side": "SELL", "qty": 30, "exec": "LOC", "price": 55.0},
        ],
    }
    plan = {"holdings_qty": 40}
    orders = prepare_loc_submit_orders(filtered, plan)
    moc_count = sum(
        1 for o in orders
        if str(o.get("exec", "")).upper() == "MOC"
    )
    sell_qty = sum(int(o.get("qty") or 0) for o in orders if o.get("side") == "SELL")
    assert moc_count == 1
    assert sell_qty == 40


def test_prepare_loc_submit_orders_caps_over_holdings():
    filtered = {
        "buy_orders": [],
        "sell_orders": [
            {"side": "SELL", "qty": 25, "exec": "LOC", "price": 50.0},
            {"side": "SELL", "qty": 25, "exec": "LOC", "price": 55.0},
        ],
    }
    plan = {"holdings_qty": 40}
    orders = prepare_loc_submit_orders(filtered, plan)
    assert sum(int(o.get("qty") or 0) for o in orders) == 40
