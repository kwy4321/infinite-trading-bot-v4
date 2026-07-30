"""Load .env and expose application settings."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", encoding="utf-8-sig")

DATA_DIR = ROOT / "data" / "accounts" / "default"
SYMBOLS = ("TQQQ", "SOXL")
SPLIT_OPTIONS = (20, 30, 40, 50, 60)
PREMIUM_OPTIONS = (5, 10, 15, 20)
TAKE_PROFIT_OPTIONS = (10, 15, 20, 25, 30)

_SPREADSHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
_DEFAULT_SA_PATH = ROOT / "data" / "google-service-account.json"
_SA_CACHE = ROOT / "data" / ".google-service-account.cache.json"


def _clean_env(raw: str) -> str:
    return (raw or "").strip().strip('"').strip("'").strip()


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        val = os.getenv(name)
        if val is not None and str(val).strip():
            return _clean_env(str(val))
    return default


def _env_bool(*names: str, default: bool = False) -> bool:
    raw = _env_first(*names)
    if not raw:
        return default
    return raw.lower() in ("true", "1", "yes", "on")


def extract_spreadsheet_id(raw: str) -> str:
    """ID만 또는 Sheets URL 모두 허용."""
    text = _clean_env(raw)
    if not text:
        return ""
    match = _SPREADSHEET_ID_RE.search(text)
    if match:
        return match.group(1)
    if "http" in text or "/" in text:
        return ""
    return text


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
        default_factory=lambda: _env_bool(
            "GOOGLE_SHEETS_ENABLED",
            "GOOGLE_SHEET_ENABLED",
            "SHEETS_ENABLED",
        ),
    )
    google_spreadsheet_id: str = field(
        default_factory=lambda: _env_first(
            "GOOGLE_SPREADSHEET_ID",
            "GOOGLE_SHEET_ID",
            "SPREADSHEET_ID",
        ),
    )
    google_service_account_json: str = field(
        default_factory=lambda: _env_first(
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GOOGLE_SERVICE_ACCOUNT_FILE",
        ),
    )
    google_sheets_url: str = field(
        default_factory=lambda: _env_first(
            "GOOGLE_SHEETS_URL",
            "GOOGLE_SHEET_URL",
            "SHEETS_URL",
        ),
    )
    streamlit_url: str = field(default_factory=lambda: os.getenv("STREAMLIT_URL", ""))
    streamlit_password: str = field(default_factory=lambda: os.getenv("STREAMLIT_PASSWORD", ""))

    @property
    def resolved_spreadsheet_id(self) -> str:
        sid = extract_spreadsheet_id(self.google_spreadsheet_id)
        if sid:
            return sid
        return extract_spreadsheet_id(self.google_sheets_url)

    @property
    def sheets_active(self) -> bool:
        """동기화 가능 — ID + 서비스 계정 JSON."""
        return bool(self.resolved_spreadsheet_id and resolve_service_account_path(self.google_service_account_json))

    @property
    def has_google_sheets(self) -> bool:
        if self.google_sheets_enabled:
            return self.sheets_active
        # ENABLED 없어도 ID+JSON 있으면 자동 활성
        return self.sheets_active

    @property
    def google_sheets_link(self) -> str:
        if self.google_sheets_url:
            url = _normalize_http_url(self.google_sheets_url)
            if url:
                return url
        sid = self.resolved_spreadsheet_id
        if sid:
            return f"https://docs.google.com/spreadsheets/d/{sid}"
        return ""

    @property
    def streamlit_link(self) -> str:
        """텔레그램 URL 버튼용 — 공백·따옴표 제거, http:// 자동 보정."""
        return _normalize_http_url(self.streamlit_url)

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


def resolve_service_account_path(raw: str = "") -> Path | None:
    """서비스 계정 JSON — 경로·기본 위치·GOOGLE_APPLICATION_CREDENTIALS·인라인 JSON."""
    text = _clean_env(raw)
    inline = text.startswith("{")
    candidates: list[Path] = []

    if inline:
        try:
            _SA_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _SA_CACHE.write_text(text, encoding="utf-8")
            return _SA_CACHE
        except OSError:
            return None

    if text:
        candidates.append(Path(text))
    gac = _clean_env(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
    if gac:
        candidates.append(Path(gac))
    candidates.extend([
        _DEFAULT_SA_PATH,
        ROOT / "google-service-account.json",
        Path.home() / "google-service-account.json",
    ])

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path
        under_root = ROOT / path
        if under_root.is_file():
            return under_root
    return None


def google_sheets_issues(settings: "Settings") -> list[str]:
    """장부/Sheets 미동작 시 .env 에서 무엇이 빠졌는지."""
    issues: list[str] = []
    if not settings.resolved_spreadsheet_id:
        issues.append("GOOGLE_SPREADSHEET_ID (또는 GOOGLE_SHEETS_URL에 전체 주소)")
    if not resolve_service_account_path(settings.google_service_account_json):
        if _env_first("GOOGLE_SHEETS_API_KEY", "GOOGLE_API_KEY"):
            issues.append(
                "API키만 설정됨 — Google Sheets 연동에는 서비스계정 JSON 파일이 필요합니다",
            )
        else:
            issues.append(
                "서비스계정 JSON 없음 — data/google-service-account.json 배치 또는 "
                "GOOGLE_SERVICE_ACCOUNT_JSON 경로 설정",
            )
    return issues


def reload_settings() -> Settings:
    """런타임 .env 재로드 (봇 재시작 없이 장부 설정 반영)."""
    load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
    return Settings()


def get_settings() -> Settings:
    return Settings()
