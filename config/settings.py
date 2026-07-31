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
    s = (raw or "").strip().strip("\r")
    if not s:
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1].strip()
    # GOOGLE_API_KEY=AIza... # 주석
    if " #" in s:
        s = s.split(" #", 1)[0].rstrip()
    elif "#" in s:
        s = re.sub(r"\s+#.*$", "", s).rstrip()
    return s.strip('"').strip("'").strip()


_ENV_KEY_ALIASES: dict[str, str] = {
    "GOOGLE_APIKEY": "GOOGLE_API_KEY",
    "GEMINI_KEY": "GEMINI_API_KEY",
    "SUMMARIZER_KEY": "SUMMARIZER_API_KEY",
}


def _normalize_env_key(key: str) -> str:
    k = (key or "").strip()
    return _ENV_KEY_ALIASES.get(k.upper(), k)


_SUMMARIZER_KEY_NAMES = (
    "SUMMARIZER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "GOOGLE_AI_API_KEY",
    "GENAI_API_KEY",
    "GOOGLE_GENAI_API_KEY",
)

_OPENAI_KEY_NAMES = ("OPENAI_API_KEY", "OPENAI_KEY")


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip().strip("\r")
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = _normalize_env_key(key.strip().lstrip("\ufeff"))
    val = _clean_env(val)
    if not key or not val:
        return None
    return key, val


_INLINE_ENV_RE = re.compile(
    r"(SUMMARIZER_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY|"
    r"GOOGLE_GENERATIVE_AI_API_KEY|OPENAI_API_KEY|"
    r"TELEGRAM_BOT_TOKEN|TELEGRAM_ALLOWED_CHAT_IDS|"
    r"TOSS_CLIENT_ID|TOSS_CLIENT_SECRET)\s*=\s*([^\s#]+)",
    re.IGNORECASE,
)


def _parse_inline_env_pairs(line: str) -> list[tuple[str, str]]:
    """# 주석 뒤 KEY=값 이 한 줄에 붙은 경우 (Windows .env 흔한 실수)."""
    out: list[tuple[str, str]] = []
    for m in _INLINE_ENV_RE.finditer(line):
        key = _normalize_env_key(m.group(1))
        val = _clean_env(m.group(2))
        if key and val:
            out.append((key, val))
    return out


_GEMINI_KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{30,}")
_OPENAI_KEY_RE = re.compile(r"sk-[0-9A-Za-z_-]{20,}")

_ENV_FILE_CANDIDATES = (".env", "data/.env", "data/secrets.env")


def env_file_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for rel in _ENV_FILE_CANDIDATES:
        for base in (ROOT, Path.cwd()):
            p = (base / rel).resolve()
            key = str(p)
            if key not in seen:
                seen.add(key)
                paths.append(p)
    extra = ROOT / "data" / "gemini_api_key.txt"
    if extra.is_file():
        paths.append(extra)
    return paths


def _read_text_multi_encoding(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "cp949", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _read_dotenv_pairs() -> dict[str, str]:
    """.env 직접 파싱 — dotenv가 놓치는 export/공백/인코딩 보완."""
    pairs: dict[str, str] = {}
    for env_path in env_file_paths():
        if not env_path.is_file():
            continue
        if env_path.name == "gemini_api_key.txt":
            try:
                val = _clean_env(_read_text_multi_encoding(env_path))
                if val:
                    pairs["GOOGLE_API_KEY"] = val
            except OSError:
                pass
            continue
        try:
            text = _read_text_multi_encoding(env_path)
            for line in text.splitlines():
                parsed = _parse_env_line(line)
                if parsed:
                    pairs[parsed[0]] = parsed[1]
                for key, val in _parse_inline_env_pairs(line):
                    pairs[key] = val
        except OSError:
            pass
        try:
            for key, val in dotenv_values(env_path, encoding="utf-8-sig").items():
                if val is None:
                    continue
                cleaned = _clean_env(str(val))
                if cleaned:
                    pairs[_normalize_env_key(key)] = cleaned
        except OSError:
            pass
    return pairs


def _scan_raw_env_for_api_key() -> tuple[str, str]:
    """변수명이 달라도 .env 본문에서 Gemini/OpenAI 키 패턴 추출."""
    for env_path in env_file_paths():
        if not env_path.is_file():
            continue
        try:
            text = _read_text_multi_encoding(env_path)
        except OSError:
            continue
        for pattern, src in (
            (r"(?:GOOGLE|GEMINI|SUMMARIZER)[\w]*API[\w]*KEY\s*=\s*['\"]?(AIza[^\"'\s#]+)", "regex:.env:AIza"),
            (r"(?:OPENAI)[\w]*API[\w]*KEY\s*=\s*['\"]?(sk-[^\"'\s#]+)", "regex:.env:sk"),
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return _clean_env(m.group(1)), src
        m = _GEMINI_KEY_RE.search(text)
        if m:
            return m.group(0), f"regex:AIza@{env_path.name}"
        m = _OPENAI_KEY_RE.search(text)
        if m:
            return m.group(0), f"regex:sk@{env_path.name}"
    return "", ""


def _read_llm_key_raw_from_env() -> tuple[str, str]:
    """형식 검증 없이 .env / gemini.txt 에서 LLM 키 후보 추출."""
    env_path = ROOT / ".env"
    if env_path.is_file():
        try:
            text = _read_text_multi_encoding(env_path)
        except OSError:
            text = ""
        if text:
            for name in _SUMMARIZER_KEY_NAMES:
                pat = rf"(?m)^[ \t]*{re.escape(name)}[ \t]*=[ \t]*([^\s#]+)"
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    val = _clean_env(m.group(1))
                    if val:
                        return val, f"file:{name}"
            for key, val in _parse_inline_env_pairs(text.replace("\n", " ")):
                if key in _SUMMARIZER_KEY_NAMES or key == "GOOGLE_API_KEY":
                    return val, f"inline:{key}"
    path = ROOT / "data" / "gemini_api_key.txt"
    if path.is_file():
        try:
            val = _clean_env(_read_text_multi_encoding(path))
            if val:
                return val, "data/gemini_api_key.txt"
        except OSError:
            pass
    return "", ""


def _read_llm_key_direct_from_env() -> tuple[str, str]:
    """유효한 Gemini/OpenAI 키만 반환."""
    val, src = _read_llm_key_raw_from_env()
    if val and _accept_llm_key(val, "gemini"):
        return val, src
    val2, src2 = _scan_raw_env_for_api_key()
    if val2:
        return val2, src2
    if val and _accept_llm_key(val, "openai"):
        return val, src
    return "", ""


def _scan_environ_for_llm_key() -> tuple[str, str]:
    """systemd·os.environ — AIza/sk- 형식만."""
    for k, v in os.environ.items():
        cleaned = _clean_env(str(v))
        if _accept_llm_key(cleaned, "gemini"):
            return cleaned, f"env:{k}"
        if _accept_llm_key(cleaned, "openai"):
            return cleaned, f"env:{k}"
    return "", ""


def probe_llm_key_in_env_file() -> dict:
    """진단 — 파일에 키 줄/AIza 패턴 있는지 (값 노출 없음)."""
    env_path = ROOT / ".env"
    txt_path = ROOT / "data" / "gemini_api_key.txt"
    raw, raw_src = _read_llm_key_raw_from_env()
    valid, valid_src = resolve_summarizer_api_key("gemini")
    out = {
        "env_path": str(env_path),
        "exists": env_path.is_file(),
        "line_found": False,
        "aiza_in_file": False,
        "gemini_txt": txt_path.is_file(),
        "gemini_txt_ok": False,
        "raw_set": bool(raw),
        "raw_src": raw_src,
        "key_format": _key_format_hint(raw),
        "wrong_format": bool(raw) and not _accept_llm_key(raw, "gemini"),
        "valid_set": bool(valid),
        "valid_src": valid_src,
    }
    if not env_path.is_file():
        return out
    try:
        text = _read_text_multi_encoding(env_path)
    except OSError:
        return out
    out["aiza_in_file"] = bool(_GEMINI_KEY_RE.search(text))
    for name in _SUMMARIZER_KEY_NAMES:
        if re.search(rf"(?m)^[ \t]*{re.escape(name)}[ \t]*=", text, re.IGNORECASE):
            out["line_found"] = True
            out["line_name"] = name
            out["parsed_ok"] = bool(raw)
            out["parsed_len"] = len(raw) if raw else 0
            out["gemini_txt_ok"] = bool(valid)
            return out
    if out["aiza_in_file"]:
        out["line_found"] = True
        out["line_name"] = "regex:AIza"
        out["parsed_ok"] = bool(raw)
        out["parsed_len"] = len(raw) if raw else 0
    out["gemini_txt_ok"] = bool(valid)
    return out


_ENV_FILE_CACHE: dict[str, str] = {}


def _env_lookup_ci(name: str) -> str:
    """대소문자 무시 — .env 캐시가 systemd/기존 os.environ 보다 우선."""
    target = name.upper()
    for k, v in _ENV_FILE_CACHE.items():
        if k.upper() == target and v:
            return v
    if val := os.getenv(name):
        cleaned = _clean_env(str(val))
        if cleaned:
            return cleaned
    return ""


def _scan_fuzzy_llm_key() -> tuple[str, str]:
    """SUMMARIZER / GEMINI / GOOGLE_API 등 이름 변형."""
    for k, v in _ENV_FILE_CACHE.items():
        if not v or len(v) < 10:
            continue
        ku = k.upper().replace("-", "_")
        if "API" not in ku and "KEY" not in ku:
            continue
        if any(tag in ku for tag in ("SUMMARIZER", "GEMINI", "GENAI", "OPENAI")):
            return v, k
        if ku in ("GOOGLE_API_KEY", "GOOGLE_APIKEY"):
            return v, k
    return "", ""


def resolve_summarizer_api_key(provider: str = "gemini") -> tuple[str, str]:
    """브리핑 AI용 API 키 — 항상 .env 최신 반영."""
    _apply_env_file()
    # systemd EnvironmentFile / os.environ 꼬임 방지 — 파일 직접 읽기 우선
    val, src = _read_llm_key_direct_from_env()
    if val:
        return val, src
    prov = (provider or "gemini").lower()
    if prov == "openai":
        for name in _OPENAI_KEY_NAMES:
            val = _env_lookup_ci(name)
            if val and _accept_llm_key(val, "openai"):
                return val, name
    for name in _SUMMARIZER_KEY_NAMES:
        val = _env_lookup_ci(name)
        if val and _accept_llm_key(val, prov):
            return val, name
        from_file = _read_key_file(name)
        if from_file and _accept_llm_key(from_file, prov):
            return from_file, f"{name}_FILE"
    val, src = _scan_fuzzy_llm_key()
    if val and _accept_llm_key(val, prov):
        return val, src
    val, src = _scan_environ_for_llm_key()
    if val:
        return val, src
    return "", ""


def list_env_file_key_names() -> list[str]:
    _apply_env_file()
    return sorted(_ENV_FILE_CACHE.keys(), key=str.upper)


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
        return _clean_env(_read_text_multi_encoding(path))
    except OSError:
        return ""


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        val = _env_lookup_ci(name)
        if val:
            return val
    for name in names:
        from_file = _read_key_file(name)
        if from_file:
            return from_file
    return default


def _env_first_with_source(*names: str) -> tuple[str, str]:
    for name in names:
        val = _env_lookup_ci(name)
        if val:
            src = name if os.getenv(name) else f".env:{name}"
            return val, src
    for name in names:
        from_file = _read_key_file(name)
        if from_file:
            return from_file, f"{name}_FILE"
    val, src = _scan_fuzzy_llm_key()
    if val:
        return val, src
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
    # summarizer_api_key → @property (항상 .env 재조회)
    summarizer_provider: str = field(
        default_factory=lambda: (_env_first("SUMMARIZER_PROVIDER") or "gemini").lower(),
    )
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
    def summarizer_api_key(self) -> str:
        key, _ = resolve_summarizer_api_key(self.summarizer_provider)
        return key

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
        if resolve_summarizer_api_key(settings.summarizer_provider)[0]:
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
    env_files = [str(p) for p in env_file_paths() if p.is_file()]
    sa_path = resolve_service_account_path(settings.google_service_account_json)
    summ_key, summ_src = resolve_summarizer_api_key(settings.summarizer_provider)
    key_names = list_env_file_key_names()
    llm_like = [k for k in key_names if "API" in k.upper() or "GEMINI" in k.upper() or "SUMMARIZER" in k.upper()]
    notes: list[str] = []
    if not summ_key:
        if not (ROOT / ".env").is_file():
            notes.append(f".env 파일 없음 — VM {ROOT}/.env 필요 (cloudshell_bot.sh restart 로 업로드)")
        elif llm_like:
            notes.append(f".env에 변수는 있음({', '.join(llm_like[:5])}) — 값 형식 확인 (AIza… 한 줄)")
        elif key_names:
            notes.append(f".env 변수 {len(key_names)}개 로드됨 — SUMMARIZER_API_KEY 또는 GOOGLE_API_KEY=AIza… 추가")
        else:
            notes.append(".env가 비어 있거나 읽기 실패 — UTF-8 저장·재업로드")
        notes.append("PC .env 수정만으로는 VM에 반영 안 됨 — Cloud Shell .env 업로드 후 restart")
        notes.append("또는 data/gemini_api_key.txt 에 키만 한 줄 저장 가능")
    if summ_key and not sa_path:
        notes.append(
            "GOOGLE_API_KEY = Gemini 브리핑용. Google Sheets 장부는 API키와 별개(JSON 필요)"
        )
    if settings.dry_run and settings.has_toss:
        notes.append("DRY_RUN=true — 텔레그램 설정→💹 실거래 켜기 또는 DRY_RUN=false")
    return {
        "env_path": env_path,
        "env_exists": (ROOT / ".env").is_file(),
        "env_files_found": env_files,
        "toss_client_id_set": bool(settings.toss_client_id),
        "toss_client_secret_set": bool(settings.toss_client_secret),
        "has_toss": settings.has_toss,
        "dry_run": settings.dry_run,
        "telegram_chat_ids_set": bool(settings.telegram_allowed_chat_ids),
        "summarizer_key_set": bool(summ_key),
        "summarizer_key_from": summ_src,
        "briefing_enabled": settings.briefing_enabled,
        "spreadsheet_id_set": bool(settings.resolved_spreadsheet_id),
        "service_account_set": sa_path is not None,
        "service_account_path": str(sa_path) if sa_path else "",
        "has_google_sheets": settings.has_google_sheets,
        "env_key_names": key_names,
        "env_llm_key_names": llm_like,
        "notes": notes,
    }


def reload_settings() -> Settings:
    """런타임 .env 재로드 (봇 재시작 없이 설정 반영)."""
    _apply_env_file()
    return Settings()


def get_settings() -> Settings:
    for p in env_file_paths():
        if p.is_file() and p.name != "gemini_api_key.txt":
            load_dotenv(p, encoding="utf-8-sig", override=True)
    _apply_env_file()
    return Settings()


# 모듈 import 시 .env 캐시 초기화
_apply_env_file()
