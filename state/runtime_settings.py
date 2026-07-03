"""Global runtime flags: pause, active symbols."""

import json
import threading
from pathlib import Path

from config.settings import ROOT, SYMBOLS

RUNTIME_PATH = ROOT / "data" / "runtime_settings.json"

DEFAULT = {
    "paused": False,
    "active_symbols": ["TQQQ"],
    "default_symbol": "TQQQ",
    "premium_pct_default": 10,
}


def _normalize_active_symbols(data: dict) -> list:
    """활성 종목 목록 정규화 — SYMBOLS 순서 유지, 유효 종목만."""
    active = data.get("active_symbols", DEFAULT["active_symbols"])
    if not isinstance(active, list):
        active = list(DEFAULT["active_symbols"])
    return [s for s in SYMBOLS if s in {x.upper() for x in active}]


class RuntimeSettings:
    def __init__(self, path: Path = RUNTIME_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: dict | None = None

    def load(self) -> dict:
        with self._lock:
            if self._cache is not None:
                return dict(self._cache)
            if not self.path.exists():
                self._cache = dict(DEFAULT)
                return dict(self._cache)
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._cache = dict(DEFAULT)
                return dict(self._cache)
            merged = dict(DEFAULT)
            merged.update(data)
            merged["active_symbols"] = _normalize_active_symbols(merged)
            self._cache = merged
            return dict(self._cache)

    def save(self, data: dict) -> None:
        with self._lock:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._cache = dict(data)

    def is_paused(self) -> bool:
        return bool(self.load().get("paused", False))

    def set_paused(self, paused: bool) -> None:
        data = self.load()
        data["paused"] = paused
        self.save(data)

    def active_symbols(self) -> list:
        active = _normalize_active_symbols(self.load())
        if active:
            return active
        default_sym = self.default_symbol()
        return [default_sym] if default_sym in SYMBOLS else list(DEFAULT["active_symbols"])

    def is_active(self, symbol: str) -> bool:
        return symbol.upper() in [s.upper() for s in self.active_symbols()]

    def set_active_symbols(self, symbols: list) -> None:
        data = self.load()
        data["active_symbols"] = [s for s in SYMBOLS if s in {x.upper() for x in symbols}]
        self.save(data)

    def toggle_active_symbol(self, symbol: str) -> list:
        """@deprecated — select_trading_symbol 사용."""
        active, _, _ = self.select_trading_symbol(symbol)
        return active

    def select_trading_symbol(self, symbol: str) -> tuple[list, str, str | None]:
        """거래 종목 버튼: OFF→켜기+편집, ON(다른 편집중)→편집 전환, ON(편집중)→끄기.

        Returns: (active_symbols, default_symbol, alert_message)
        """
        data = self.load()
        active = {s.upper() for s in data.get("active_symbols", DEFAULT["active_symbols"])}
        sym = symbol.upper()
        if sym not in SYMBOLS:
            return self.active_symbols(), self.default_symbol(), None

        default = str(data.get("default_symbol", DEFAULT["default_symbol"])).upper()

        if sym not in active:
            active.add(sym)
            data["default_symbol"] = sym
        elif sym != default:
            data["default_symbol"] = sym
        elif len(active) <= 1:
            return (
                [s for s in SYMBOLS if s in active],
                default,
                "최소 1개 종목은 켜져 있어야 해요.",
            )
        else:
            active.discard(sym)
            ordered = [s for s in SYMBOLS if s in active]
            data["default_symbol"] = ordered[0]

        ordered = [s for s in SYMBOLS if s in active]
        data["active_symbols"] = ordered
        self.save(data)
        return ordered, data["default_symbol"], None

    def default_symbol(self) -> str:
        return self.load().get("default_symbol", "TQQQ")

    def set_default_symbol(self, symbol: str) -> None:
        data = self.load()
        sym = symbol.upper()
        data["default_symbol"] = sym
        if sym in SYMBOLS:
            data["active_symbols"] = [sym]
        self.save(data)

    def premium_default(self) -> int:
        return int(self.load().get("premium_pct_default", 10))

    def set_premium_default(self, pct: int) -> None:
        data = self.load()
        data["premium_pct_default"] = int(pct)
        self.save(data)
