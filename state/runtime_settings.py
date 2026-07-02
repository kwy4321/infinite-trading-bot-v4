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

    def load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                return dict(DEFAULT)
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                return dict(DEFAULT)
            merged = dict(DEFAULT)
            merged.update(data)
            merged["active_symbols"] = _normalize_active_symbols(merged)
            return merged

    def save(self, data: dict) -> None:
        with self._lock:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

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
        """종목 자동매매 ON/OFF 토글. 갱신된 활성 종목 리스트를 반환."""
        data = self.load()
        active = {s.upper() for s in data.get("active_symbols", list(SYMBOLS))}
        sym = symbol.upper()
        if sym in active:
            active.discard(sym)
        else:
            active.add(sym)
        ordered = [s for s in SYMBOLS if s in active]
        data["active_symbols"] = ordered
        self.save(data)
        return ordered

    def default_symbol(self) -> str:
        return self.load().get("default_symbol", "TQQQ")

    def set_default_symbol(self, symbol: str) -> None:
        data = self.load()
        sym = symbol.upper()
        data["default_symbol"] = sym
        # 기본종목 선택 = 주문계획·자동매매 대상도 해당 종목만
        if sym in SYMBOLS:
            data["active_symbols"] = [sym]
        self.save(data)

    def premium_default(self) -> int:
        return int(self.load().get("premium_pct_default", 10))

    def set_premium_default(self, pct: int) -> None:
        data = self.load()
        data["premium_pct_default"] = int(pct)
        self.save(data)
