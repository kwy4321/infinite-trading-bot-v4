"""18:05 LOC 자동 접수 경로 — VM/CI 에서 run_for_symbol LIVE 스모크."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jobs.executor import JobExecutor
from strategy.order_planner import JobPhase
from tests.conftest import FakeApp


class _LiveBroker:
    dry_run = False

    def get_holdings_item(self, symbol: str) -> dict:
        return {"qty": 10, "avg_price": 50.0, "current_price": 55.0}

    def get_price(self, symbol: str) -> float:
        return 55.0

    def cancel_open_cls_orders(self, symbol: str, *, side: str | None = None) -> list:
        return []

    def place_loc_order(self, symbol: str, side: str, price: float, qty: int) -> dict:
        return {"order_id": f"smoke-{symbol}-{side}"}


async def _run() -> dict:
    app = FakeApp(dry=False, active=("TQQQ",))
    app.broker = _LiveBroker()
    executor = JobExecutor(app, sender=None)
    return await executor.run_for_symbol(
        "TQQQ",
        JobPhase.JOB3_LOC_CLOSE,
        submit_at_open=True,
        notify_per_order=False,
    )


def test_live_loc_submit_path() -> None:
    result = asyncio.run(_run())
    if result.get("total", 0) <= 0:
        raise AssertionError(f"LOC submit path returned no orders: {result}")
    if result.get("submitted", 0) <= 0:
        raise AssertionError(f"LOC submit path did not submit: {result}")
    line = result.get("line", "")
    if "UnboundLocalError" in line or "is_dry" in line and "실패" in line:
        raise AssertionError(f"LOC submit path error: {line}")


def main() -> None:
    test_live_loc_submit_path()
    print("test_loc_submit_path OK")


if __name__ == "__main__":
    main()
