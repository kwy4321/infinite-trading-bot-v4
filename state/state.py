"""Per-symbol JSON state (TQQQ / SOXL)."""

import threading
import datetime
from pathlib import Path
from typing import Optional

from account.account import AccountPaths
from config.json_io import load_json, save_json
from config.settings import SYMBOLS

DEFAULT_STATE = {
    "symbol": "",
    "mode": "normal",
    "split_count": 40,
    "principal": 10000.0,
    "take_profit_pct": 0.0,
    "force_one": False,
    "T": 0.0,
    "qty": 0,
    "avg_price": 0.0,
    "pending_buy_orders": [],
    "pending_sell_orders": [],
    "close_prices": [],
    "split_log": [],
    "fill_log": [],
    "tracked_orders": [],
    "last_t_qty": 0,
    "last_order_date": "",
    "last_updated": "",
}


class StateStore:
    def __init__(self, paths: Optional[AccountPaths] = None):
        self.paths = paths or AccountPaths()
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _default(self, symbol: str) -> dict:
        s = dict(DEFAULT_STATE)
        s["symbol"] = symbol.upper()
        return s

    def load(self, symbol: str) -> dict:
        symbol = symbol.upper()
        path = self.paths.symbol_state(symbol)
        with self._lock:
            if not path.exists():
                state = self._default(symbol)
                self._save_unlocked(symbol, state)
                return state
            data = load_json(path, self._default(symbol))
            merged = self._default(symbol)
            merged.update(data)
            if "principal" not in data and "cash" in data:
                merged["principal"] = float(data["cash"])
            merged.pop("cash", None)
            merged["symbol"] = symbol
            return merged

    def save(self, symbol: str, state: dict) -> None:
        symbol = symbol.upper()
        state["symbol"] = symbol
        state["last_updated"] = datetime.datetime.now().astimezone().isoformat()
        with self._lock:
            self._save_unlocked(symbol, state)

    def _save_unlocked(self, symbol: str, state: dict) -> None:
        path = self.paths.symbol_state(symbol)
        save_json(path, state, compact=True)

    def set_principal(self, symbol: str, amount: float) -> dict:
        state = self.load(symbol)
        state["principal"] = max(0.0, float(amount))
        self.save(symbol, state)
        return state

    def set_T(self, symbol: str, t_val: float) -> dict:
        state = self.load(symbol)
        state["T"] = float(t_val)
        self.save(symbol, state)
        return state

    def set_split_count(self, symbol: str, count: int) -> dict:
        state = self.load(symbol)
        state["split_count"] = int(count)
        self.save(symbol, state)
        return state

    def set_take_profit(self, symbol: str, pct: float) -> dict:
        state = self.load(symbol)
        state["take_profit_pct"] = max(0.0, float(pct))
        self.save(symbol, state)
        return state

    def set_force_one(self, symbol: str, enabled: bool) -> dict:
        state = self.load(symbol)
        state["force_one"] = bool(enabled)
        self.save(symbol, state)
        return state

    def sync_holdings(self, symbol: str, qty: int, avg_price: float) -> dict:
        state = self.load(symbol)
        state["qty"] = int(qty)
        state["avg_price"] = float(avg_price)
        self.save(symbol, state)
        return state

    def list_symbols(self):
        return SYMBOLS
