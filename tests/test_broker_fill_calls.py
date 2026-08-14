"""list_broker_fills — 토스 조회 왕복 횟수 (ORDER_HISTORY 는 초당 4회 제한)."""

from __future__ import annotations

import pytest

from broker.toss_client import TossClient


class CountingClient(TossClient):
    """네트워크 없이 조회 횟수만 세는 TossClient."""

    def __init__(self, closed_orders=None, details=None):
        self.dry_run = False
        self._fills_cache = {}
        self._order_cache = {}
        self._closed_orders = list(closed_orders or [])
        self._details = dict(details or {})
        self.closed_calls: list[dict] = []
        self.order_calls: list[str] = []

    def get_closed_orders(self, symbol=None, *, limit=100, max_orders=200, from_date=None):
        self.closed_calls.append({"symbol": symbol, "from_date": from_date})
        return [o for o in self._closed_orders if not symbol or o["symbol"] == symbol]

    def get_order(self, order_id):
        self.order_calls.append(order_id)
        return self._details.get(order_id, {})


def _closed_order(oid: str, symbol="TQQQ", price=50.0, qty=3):
    return {
        "orderId": oid,
        "symbol": symbol,
        "side": "BUY",
        "status": "FILLED",
        "quantity": qty,
        "orderedAt": "2026-08-10T22:35:00+09:00",
        "execution": {
            "filledQuantity": qty,
            "averageFilledPrice": price,
            "filledAt": "2026-08-11T05:00:00+09:00",
        },
    }


def _log_entry(oid: str, symbol="TQQQ", price=50.0, qty=3):
    return {
        "order_id": oid,
        "symbol": symbol,
        "side": "BUY",
        "qty": qty,
        "price": price,
        "ordered_at": "2026-03-02T22:35:00+09:00",
        "filled_at": "2026-03-03T05:00:00+09:00",
    }


def test_known_fills_replace_per_order_lookups():
    """fill_log 에 이미 있는 주문은 단건 조회하지 않는다 (누적될수록 컸던 비용)."""
    history = [f"old-{i}" for i in range(120)]
    client = CountingClient(closed_orders=[_closed_order("recent-1")])

    fills = client.list_broker_fills(
        "TQQQ",
        extra_order_ids=history,
        known_fills=[_log_entry(oid) for oid in history],
    )

    assert client.order_calls == []
    assert len(fills) == len(history) + 1


def test_without_known_fills_every_id_costs_a_lookup():
    """회귀 감시 — known_fills 를 빼면 예전처럼 건당 왕복이 생긴다."""
    history = [f"old-{i}" for i in range(5)]
    client = CountingClient(closed_orders=[_closed_order("recent-1")])

    client.list_broker_fills("TQQQ", extra_order_ids=history)

    assert client.order_calls == history


def test_closed_list_stops_after_first_successful_attempt():
    """날짜 필터 조회가 성공하면 전체 재조회를 하지 않는다."""
    client = CountingClient(closed_orders=[_closed_order("recent-1")])

    client.list_broker_fills("TQQQ")

    assert len(client.closed_calls) == 1
    assert client.closed_calls[0]["from_date"] is not None


def test_terminal_order_detail_is_fetched_once():
    client = CountingClient(
        closed_orders=[],
        details={
            "oid-1": {
                "order_id": "oid-1", "symbol": "TQQQ", "side": "BUY",
                "status": "FILLED", "filled_quantity": 2,
                "average_filled_price": 51.0,
                "ordered_at": "2026-08-10T22:35:00+09:00",
                "filled_at": "2026-08-11T05:00:00+09:00",
            },
        },
    )

    client.list_broker_fills("TQQQ", extra_order_ids=["oid-1"])
    client._fills_cache.clear()
    client.list_broker_fills("TQQQ", extra_order_ids=["oid-1"])

    assert client.order_calls == ["oid-1"]


def test_known_fills_ignore_other_symbols():
    client = CountingClient(closed_orders=[])

    fills = client.list_broker_fills(
        "TQQQ",
        extra_order_ids=["soxl-1"],
        known_fills=[_log_entry("soxl-1", symbol="SOXL")],
    )

    assert fills == []
    assert client.order_calls == ["soxl-1"]


@pytest.mark.parametrize("entry", [
    {"order_id": "", "qty": 1, "price": 1.0, "ordered_at": "2026-01-01"},
    {"order_id": "a", "qty": 0, "price": 1.0, "ordered_at": "2026-01-01"},
    {"order_id": "a", "qty": 1, "price": 0, "ordered_at": "2026-01-01"},
    {"order_id": "a", "qty": 1, "price": 1.0},
])
def test_incomplete_log_entries_are_not_trusted(entry):
    assert TossClient._fill_from_log_entry(entry) is None
