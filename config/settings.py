"""Load .env and expose application settings."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

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


_ENV_FILE_CACHE: dict[str, str] = {}

_SUMMARIZER_KEY_NAMES = (
    "SUMMARIZER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "GOOGLE_AI_API_KEY",
)


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = key.strip()
    val = _clean_env(val)
    if not key or not val:
        return None
    return key, val


def _read_dotenv_pairs() -> dict[str, str]:
    """.env 직접 파싱 — dotenv가 놓치는 export/공백 형식 보완."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return {}
    pairs: dict[str, str] = {}
    try:
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            parsed = _parse_env_line(line)
            if parsed:
                pairs[parsed[0]] = parsed[1]
    except OSError:
        pass
    try:
        for key, val in dotenv_values(env_path, encoding="utf-8-sig").items():
            if val is None:
                continue
            cleaned = _clean_env(str(val))
            if cleaned:
                pairs[key] = cleaned
    except OSError:
        pass
    return pairs


def _read_key_file(env_name: str) -> str:
    """KEY_FILE=/path/to/secret.txt 형식."""
    path_raw = _ENV_FILE_CACHE.get(f"{env_name}_FILE") or os.getenv(f"{env_name}_FILE", "")
    path_raw = _clean_env(path_raw)
    if not path_raw:
        return ""
    path = Path(path_raw)
    if not path.is_file():
        path = ROOT / path_raw
    if not path.is_file():
        return ""
    try:
        return _clean_env(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return ""


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        val = os.getenv(name)
        if val is not None and str(val).strip():
            return _clean_env(str(val))
    for name in names:
        val = _ENV_FILE_CACHE.get(name)
        if val:
            return val
    for name in names:
        from_file = _read_key_file(name)
        if from_file:
            return from_file
    return default


def _env_first_with_source(*names: str) -> tuple[str, str]:
    for name in names:
        val = os.getenv(name)
        if val is not None and str(val).strip():
            return _clean_env(str(val)), name
    for name in names:
        val = _ENV_FILE_CACHE.get(name)
        if val:
            return val, f".env:{name}"
    for name in names:
        from_file = _read_key_file(name)
        if from_file:
            return from_file, f"{name}_FILE"
    return "", ""


def _apply_env_file() -> None:
    """.env 재적용 — 빈 값은 기존 환경 변수를 지우지 않음 (systemd·VM 안전)."""
    global _ENV_FILE_CACHE
    _ENV_FILE_CACHE = _read_dotenv_pairs()
    for key, val in _ENV_FILE_CACHE.items():
        if val:
            os.environ[key] = val


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


def is_dry_mode(settings: "Settings", *, force_live: bool = False) -> bool:
    """LIVE = Toss 키 있음 + (DRY_RUN 꺼짐 또는 force_live)."""
    if force_live and settings.has_toss:
        return False
    return settings.dry_run or not settings.has_toss


@dataclass
class Settings:
    toss_client_id: str = field(default_factory=lambda: _env_first("TOSS_CLIENT_ID"))
    toss_client_secret: str = field(default_factory=lambda: _env_first("TOSS_CLIENT_SECRET"))
    toss_account_seq: str = field(default_factory=lambda: _env_first("TOSS_ACCOUNT_SEQ", default="1"))
    telegram_bot_token: str = field(default_factory=lambda: _env_first("TELEGRAM_BOT_TOKEN"))
    telegram_allowed_chat_ids: tuple = field(default_factory=lambda: _parse_chat_ids())
    dry_run: bool = field(default_factory=lambda: _env_bool("DRY_RUN", default=False))
    news_api_key: str = field(default_factory=lambda: _env_first("NEWS_API_KEY"))
    summarizer_api_key: str = field(
        default_factory=lambda: _env_first(*_SUMMARIZER_KEY_NAMES),
    )
    # 뉴스 요약 LLM: gemini | openai (키가 있을 때만 동작). 모델은 비우면 기본값(gemini-2.5-flash) 사용.
    summarizer_provider: str = field(default_factory=lambda: os.getenv("SUMMARIZER_PROVIDER", "gemini").lower())
    summarizer_model: str = field(default_factory=lambda: os.getenv("SUMMARIZER_MODEL", ""))
    # GCP e2-micro 등 소형 VM — 디스크·RAM 절약
    backup_enabled: bool = field(default_factory=lambda: os.getenv("BACKUP_ENABLED", "true").lower() == "true")
    backup_keep: int = field(default_factory=lambda: _int_env("BACKUP_KEEP", 5))
    briefing_enabled: bool = field(default_factory=lambda: _env_bool("BRIEFING_ENABLED", default=True))
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
            "GOOGLE_CREDENTIALS_JSON",
            "GOOGLE_SERVICE_ACCOUNT",
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
    raw = _env_first("TELEGRAM_ALLOWED_CHAT_IDS", "CHAT_ID")
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
    if not text:
        text = _env_first(
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "GOOGLE_CREDENTIALS_JSON",
            "GOOGLE_SERVICE_ACCOUNT",
        )
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
        issues.append("GOOGLE_SPREADSHEET_ID 또는 GOOGLE_SHEETS_URL(스프레드시트 주소)")
    if not resolve_service_account_path(settings.google_service_account_json):
        if _env_first(*_SUMMARIZER_KEY_NAMES):
            issues.append(
                "Gemini API 키는 인식됨(브리핑용). "
                "Sheets 장부는 서비스계정 JSON 파일이 추가로 필요 "
                "(data/google-service-account.json)",
            )
        else:
            issues.append(
                "서비스계정 JSON 없음 — data/google-service-account.json 배치 또는 "
                "GOOGLE_SERVICE_ACCOUNT_JSON 경로 설정",
            )
    return issues


def env_diagnostics(settings: "Settings | None" = None) -> dict:
    """봇이 실제로 읽은 설정 (값 노출 없음)."""
    if settings is None:
        settings = reload_settings()
    env_path = str(ROOT / ".env")
    sa_path = resolve_service_account_path(settings.google_service_account_json)
    _, summ_src = _env_first_with_source(*_SUMMARIZER_KEY_NAMES)
    notes: list[str] = []
    if _env_first(*_SUMMARIZER_KEY_NAMES) and not sa_path:
        notes.append(
            "GOOGLE_API_KEY = Gemini 브리핑용. Google Sheets 장부는 API키와 별개(JSON 필요)"
        )
    if settings.dry_run and settings.has_toss:
        notes.append("DRY_RUN=true — 텔레그램 설정→💹 실거래 켜기 또는 DRY_RUN=false")
    return {
        "env_path": env_path,
        "env_exists": (ROOT / ".env").is_file(),
        "toss_client_id_set": bool(settings.toss_client_id),
        "toss_client_secret_set": bool(settings.toss_client_secret),
        "has_toss": settings.has_toss,
        "dry_run": settings.dry_run,
        "telegram_chat_ids_set": bool(settings.telegram_allowed_chat_ids),
        "summarizer_key_set": bool(settings.summarizer_api_key),
        "summarizer_key_from": summ_src,
        "briefing_enabled": settings.briefing_enabled,
        "spreadsheet_id_set": bool(settings.resolved_spreadsheet_id),
        "service_account_set": sa_path is not None,
        "service_account_path": str(sa_path) if sa_path else "",
        "has_google_sheets": settings.has_google_sheets,
        "notes": notes,
    }


def reload_settings() -> Settings:
    """런타임 .env 재로드 (봇 재시작 없이 설정 반영)."""
    _apply_env_file()
    return Settings()


def get_settings() -> Settings:
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    _apply_env_file()
    return Settings()


# 모듈 import 시 .env 캐시 초기화
_apply_env_file()
