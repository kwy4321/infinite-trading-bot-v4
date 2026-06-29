"""Global runtime flags: pause, active symbols."""

import json
import threading
from pathlib import Path

from config.settings import ROOT, SYMBOLS

RUNTIME_PATH = ROOT / "data" / "runtime_settings.json"

DEFAULT = {
    "paused": False,
    "active_symbols": list(SYMBOLS),
    "default_symbol": "TQQQ",
    "premium_pct_default": 10,
}


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
        return self.load().get("active_symbols", list(SYMBOLS))

    def default_symbol(self) -> str:
        return self.load().get("default_symbol", "TQQQ")

    def set_default_symbol(self, symbol: str) -> None:
        data = self.load()
        data["default_symbol"] = symbol.upper()
        self.save(data)

    def premium_default(self) -> int:
        return int(self.load().get("premium_pct_default", 10))

    def set_premium_default(self, pct: int) -> None:
        data = self.load()
        data["premium_pct_default"] = int(pct)
        self.save(data)
