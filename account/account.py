"""Account-scoped data paths (multi-account ready)."""

from pathlib import Path

from config.settings import DATA_DIR, ROOT


class AccountPaths:
    def __init__(self, account_id: str = "default"):
        self.account_id = account_id
        self.root = Path(DATA_DIR) if account_id == "default" else ROOT / "data" / "accounts" / account_id

    def symbol_state(self, symbol: str) -> Path:
        return self.root / f"{symbol.upper()}.json"

    @property
    def cycles(self) -> Path:
        return self.root / "cycles.json"

    @property
    def runtime_settings(self) -> Path:
        return ROOT / "data" / "runtime_settings.json"

    @property
    def data_root(self) -> Path:
        return ROOT / "data"

    @property
    def token_cache(self) -> Path:
        return ROOT / "data" / "token_cache.json"
