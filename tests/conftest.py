"""테스트 공용 가짜 App — 브로커·파일 접근 없이 포맷터를 검증한다."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeRuntime:
    def __init__(self, active=("TQQQ",), paused=False, premium=10):
        self._active = list(active)
        self._paused = paused
        self._premium = premium

    def active_symbols(self):
        return list(self._active)

    def is_paused(self):
        return self._paused

    def force_live(self):
        return False

    def premium_default(self):
        return self._premium


class FakeState:
    DEFAULT = {
        "T": 12.0,
        "qty": 10,
        "avg_price": 50.0,
        "principal": 10000.0,
        "split_count": 40,
        "fill_log": [],
        "take_profit_pct": 10,
    }

    def __init__(self, overrides: dict | None = None):
        self._data = {}
        self._overrides = overrides or {}

    def load(self, symbol: str) -> dict:
        symbol = symbol.upper()
        if symbol not in self._data:
            self._data[symbol] = {**self.DEFAULT, **self._overrides.get(symbol, {})}
        return dict(self._data[symbol])

    def save(self, symbol: str, st: dict) -> None:
        self._data[symbol.upper()] = dict(st)

    def list_symbols(self):
        return list(self._data)


class FakeCycles:
    def __init__(self):
        self.symbol_data = {
            "current": {
                "cycle_no": 3,
                "started_at": "2026-07-01",
                "principal": 10000.0,
                "total_buy_usd": 500.0,
                "total_sell_usd": 100.0,
                "buy_count": 2,
                "sell_count": 1,
                "trades": [],
            },
            "completed": [],
            "next_cycle_no": 4,
        }

    def get_symbol_data(self, symbol: str) -> dict:
        return self.symbol_data

    def available_cash(self, symbol: str, principal: float) -> float:
        cur = self.symbol_data["current"]
        return max(
            0.0,
            round(principal - cur["total_buy_usd"] + cur["total_sell_usd"], 2),
        )

    def cycle_progress(self, symbol: str, *, trading: bool, qty: int) -> int:
        return 3 if trading else 0

    def calc_unrealized_pnl(self, symbol, qty, avg_price, current_price) -> dict:
        return {
            "cycle_no": 3,
            "started_at": "2026-07-01",
            "cycle_pnl_usd": 42.0,
            "cycle_pnl_pct": 8.4,
        }

    def portfolio_stats(self, symbols=None, qty_by_symbol=None) -> dict:
        return {
            "realized_usd": 123.45,
            "completed_cycles": 2,
            "active_cycles": 1,
            "per_symbol": {
                "TQQQ": {
                    "cycle_progress": 3,
                    "realized_usd": 123.45,
                    "completed_cycles": 2,
                    "active": True,
                },
            },
        }


class FakeStrategy:
    def resolve_mode_from_state(self, st):
        return types.SimpleNamespace(value="NORMAL_EARLY")

    def resolve_take_profit(self, symbol, value):
        return value or 10

    def get_plan_from_state(self, symbol, price, st, premium, available_cash=0.0):
        return {
            "mode": "NORMAL_EARLY",
            "avg_price": st["avg_price"],
            "current_price": price,
            "star_pct": premium,
            "star_price": round(price * (1 + premium / 100), 2),
            "star_buy": 1,
            "take_profit_pct": 10,
            "one_buy_amount": 250.0,
            "reverse_mode": False,
            "buy_orders": [
                {"action": "STAR_BUY", "price": 55.0, "qty": 2, "desc": "별 +10%", "side": "BUY"},
            ],
            "sell_orders": [
                {"action": "TAKE_PROFIT", "price": 60.0, "qty": 5, "desc": "익절 +10%", "side": "SELL"},
            ],
        }


class FakeBroker:
    dry_run = True

    def get_holdings_overview(self):
        return {
            "totalEvaluationAmount": {"usd": "1200", "krw": "1600000"},
            "items": [
                {
                    "symbol": "TQQQ",
                    "quantity": "10",
                    "averagePurchasePrice": "50",
                    "lastPrice": "60",
                    "marketValue": {"usd": "600", "krw": "800000"},
                },
            ],
        }

    def get_holdings_item(self, symbol):
        if symbol.upper() != "TQQQ":
            return {"current_price": 0.0, "quantity": 0}
        return {"current_price": 60.0, "quantity": 10}

    def get_price(self, symbol):
        """보유하지 않은 종목은 조회 실패(0) — state 폴백 경로를 검증하려고."""
        return 60.0 if symbol.upper() == "TQQQ" else 0.0

    def get_buying_power(self, currency="USD"):
        return {"cashBuyingPower": {"usd": "600", "krw": "800000"}}

    def get_exchange_rate(self, base, quote):
        return {"rate": 1350.0}

    def get_us_market_status(self):
        return "regular"


class FakeSettings:
    """config.settings.is_dry_mode 가 읽는 필드를 그대로 흉내낸다."""

    def __init__(self, *, dry=True):
        self.has_toss = not dry
        self.dry_run = dry
        self.has_google_sheets = False
        self.briefing_enabled = False
        self.max_completed_cycles = 50
        self.log_level = "INFO"
        self.summarizer_api_key = ""
        self.backup_enabled = False
        self.backup_keep = 7


class FakeApp:
    """services/포맷터가 기대하는 App 인터페이스의 최소 구현."""

    def __init__(self, *, active=("TQQQ",), dry=True):
        self.settings = FakeSettings(dry=dry)
        self.runtime = FakeRuntime(active=active)
        self.state = FakeState()
        self.cycles = FakeCycles()
        self.strategy = FakeStrategy()
        self.broker = FakeBroker()
        self.broker.dry_run = dry

    @property
    def _dry(self) -> bool:
        """테스트에서 DRY/LIVE 를 토글하는 스위치 — 설정 필드를 함께 바꾼다."""
        return self.settings.dry_run or not self.settings.has_toss

    @_dry.setter
    def _dry(self, value: bool) -> None:
        self.settings.dry_run = bool(value)
        self.settings.has_toss = not bool(value)
        self.broker.dry_run = bool(value)

    def is_dry(self) -> bool:
        return self._dry

    def sync_broker_mode(self) -> None:
        self.broker.dry_run = self._dry


@pytest.fixture
def fake_app():
    return FakeApp()
