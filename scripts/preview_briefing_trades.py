"""아침 브리핑 무매 현황 — 직전 종가 LOC 체결 한 줄 미리보기 (푸시 전 확인용)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from briefing.strategy_briefing import format_strategy_briefing
from tests.conftest import FakeApp, FakeCycles, FakeState


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def _app_with_trades(
    *,
    symbol: str,
    session_date: str,
    trades: list[dict],
    fill_log: list[dict] | None = None,
) -> FakeApp:
    app = FakeApp(dry=True, active=(symbol,))
    app.state = FakeState(
        {
            symbol: {
                "fill_log": fill_log or [],
            },
        },
    )
    cycles = FakeCycles()
    cycles.symbol_data["current"]["trades"] = trades
    app.cycles = cycles
    return app


def main() -> None:
    session_date = "2026-03-11"
    session_label = "3/11(수)"

    scenarios = [
        (
            "체결 없음",
            _app_with_trades(symbol="TQQQ", session_date=session_date, trades=[]),
        ),
        (
            "매수 1건",
            _app_with_trades(
                symbol="TQQQ",
                session_date=session_date,
                trades=[
                    {
                        "side": "BUY",
                        "qty": 2,
                        "price": 55.0,
                        "t_before": 0.0,
                        "t_after": 0.5,
                        "filled_at": "2026-03-12T05:30:00+09:00",
                        "desc": "별 +10%",
                    },
                ],
            ),
        ),
        (
            "매수+매도",
            _app_with_trades(
                symbol="SOXL",
                session_date=session_date,
                trades=[
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
                ],
            ),
        ),
    ]

    print("=" * 60)
    print("[preview] morning briefing - session LOC one-liner")
    print(f"US session: {session_label} ({session_date})")
    print("=" * 60)

    for title, app in scenarios:
        sym = app.runtime.active_symbols()[0]
        block = format_strategy_briefing(
            app, session_date, session_label=session_label,
        )
        print(f"\n--- [{title}] {sym} ---")
        print(_strip_html(block))
        print()

    print("=" * 60)
    print("Telegram will apply HTML bold/dim formatting.")
    print("preview_briefing_trades OK")


if __name__ == "__main__":
    main()
