"""Load .env and expose application settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data" / "accounts" / "default"
SYMBOLS = ("TQQQ", "SOXL")
SPLIT_OPTIONS = (20, 30, 40, 50, 60)
PREMIUM_OPTIONS = (5, 10, 15, 20)
TAKE_PROFIT_OPTIONS = (10, 15, 20, 25, 30)


@dataclass
class Settings:
    toss_client_id: str = field(default_factory=lambda: os.getenv("TOSS_CLIENT_ID", ""))
    toss_client_secret: str = field(default_factory=lambda: os.getenv("TOSS_CLIENT_SECRET", ""))
    toss_account_seq: str = field(default_factory=lambda: os.getenv("TOSS_ACCOUNT_SEQ", "1"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_allowed_chat_ids: tuple = field(default_factory=lambda: _parse_chat_ids())
    dry_run: bool = field(default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true")
    news_api_key: str = field(default_factory=lambda: os.getenv("NEWS_API_KEY", ""))
    summarizer_api_key: str = field(default_factory=lambda: os.getenv("SUMMARIZER_API_KEY", ""))
    # 뉴스 요약 LLM: gemini | openai (키가 있을 때만 동작). 모델은 비우면 기본값(gemini-2.5-flash) 사용.
    summarizer_provider: str = field(default_factory=lambda: os.getenv("SUMMARIZER_PROVIDER", "gemini").lower())
    summarizer_model: str = field(default_factory=lambda: os.getenv("SUMMARIZER_MODEL", ""))
    # GCP e2-micro 등 소형 VM — 디스크·RAM 절약
    backup_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_ENABLED", "true").lower() == "true")
    backup_keep: int = field(default_factory=lambda: _int_env("BACKUP_KEEP", 5))
    briefing_enabled: bool = field(default_factory=lambda: os.getenv("BRIEFING_ENABLED", "true").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "WARNING").upper())
    max_split_log: int = field(default_factory=lambda: _int_env("MAX_SPLIT_LOG", 30))
    max_completed_cycles: int = field(default_factory=lambda: _int_env("MAX_COMPLETED_CYCLES", 50))
    google_sheets_enabled: bool = field(
        default_factory=lambda: os.getenv("GOOGLE_SHEETS_ENABLED", "false").lower() == "true",
    )
    google_spreadsheet_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SPREADSHEET_ID", ""))
    google_service_account_json: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
    )
    google_sheets_url: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_URL", ""))
    streamlit_url: str = field(default_factory=lambda: os.getenv("STREAMLIT_URL", ""))
    streamlit_password: str = field(default_factory=lambda: os.getenv("STREAMLIT_PASSWORD", ""))

    @property
    def has_google_sheets(self) -> bool:
        return bool(
            self.google_sheets_enabled
            and self.google_spreadsheet_id
            and self.google_service_account_json
        )

    @property
    def streamlit_link(self) -> str:
        """텔레그램 URL 버튼용 — 공백·따옴표 제거, http:// 자동 보정."""
        return _normalize_http_url(self.streamlit_url)

    @property
    def google_sheets_link(self) -> str:
        if self.google_sheets_url:
            return _normalize_http_url(self.google_sheets_url)
        if self.google_spreadsheet_id:
            return f"https://docs.google.com/spreadsheets/d/{self.google_spreadsheet_id}"
        return ""

    @property
    def has_toss(self) -> bool:
        return bool(self.toss_client_id and self.toss_client_secret)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token)


def _parse_chat_ids() -> tuple:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", os.getenv("CHAT_ID", ""))
    if not raw:
        return ()
    return tuple(int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit())


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _normalize_http_url(raw: str) -> str:
    url = (raw or "").strip().strip('"').strip("'")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url


def get_settings() -> Settings:
    return Settings()
