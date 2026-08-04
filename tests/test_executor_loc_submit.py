"""18:05 LOC 자동 접수 — run_for_symbol LIVE 경로 회귀 테스트."""

from __future__ import annotations

import asyncio

import pytest

from jobs.executor import JobExecutor
from strategy.order_planner import JobPhase
from tests.conftest import FakeApp


class _LiveBroker:
    dry_run = False
    submitted: list[tuple] = []

    def get_holdings_item(self, symbol: str) -> dict:
        return {"qty": 10, "avg_price": 50.0, "current_price": 55.0}

    def get_price(self, symbol: str) -> float:
        return 55.0

    def cancel_open_cls_orders(self, symbol: str, *, side: str | None = None) -> list:
        return []

    def place_loc_order(self, symbol: str, side: str, price: float, qty: int) -> dict:
        type(self).submitted.append((symbol, side, price, qty))
        return {"order_id": f"test-{symbol}-{side}-{len(type(self).submitted)}"}


@pytest.fixture
def live_executor():
    _LiveBroker.submitted = []
    app = FakeApp(dry=False, active=("TQQQ",))
    app.broker = _LiveBroker()
    return JobExecutor(app, sender=None)


def test_run_for_symbol_live_submit_at_open_submits_orders(live_executor):
    """is_dry 정의 전 resolve_holdings_qty 호출 시 UnboundLocalError → total=0 회귀."""
    result = asyncio.run(
        live_executor.run_for_symbol(
            "TQQQ",
            JobPhase.JOB3_LOC_CLOSE,
            submit_at_open=True,
            notify_per_order=False,
        ),
    )
    assert result.get("skipped") is not True
    assert result["total"] > 0, result
    assert result["submitted"] > 0, result
    assert "UnboundLocalError" not in result.get("line", "")
    assert "주문 없음" not in result.get("line", "")
    assert len(_LiveBroker.submitted) > 0


def test_plan_has_orders_but_submit_path_matches(live_executor):
    """계획과 동일하게 매수·매도 LOC 가 접수 대상에 포함."""
    result = asyncio.run(
        live_executor.run_for_symbol(
            "TQQQ",
            JobPhase.JOB3_LOC_CLOSE,
            submit_at_open=True,
            notify_per_order=False,
        ),
    )
    sides = {s for _, s, _, _ in _LiveBroker.submitted}
    assert "BUY" in sides or "SELL" in sides
    assert result["total"] == len(_LiveBroker.submitted)
