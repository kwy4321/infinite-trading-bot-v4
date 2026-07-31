"""Toss Open API client_id / client_secret — 형식 검증·뒤바뀜 감지."""

from __future__ import annotations

import re

_ID_PREFIXES = ("c_", "tsck_")
_SECRET_PREFIX = "s_"


def mask_credential(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "(비어 있음)"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}…{text[-4:]}"


def _looks_like_client_id(value: str) -> bool:
    text = (value or "").strip()
    return any(text.startswith(p) for p in _ID_PREFIXES)


def _looks_like_client_secret(value: str) -> bool:
    return (value or "").strip().startswith(_SECRET_PREFIX)


def _strip_credential(value: str) -> str:
    """복사·붙여넣기 잔여 문자 제거 (콤마·세미콜론·따옴표·CR)."""
    s = (value or "").strip().strip("\r").strip('"').strip("'")
    return s.rstrip(",;")


def normalize_toss_credentials(
    client_id: str,
    client_secret: str,
) -> tuple[str, str, list[str]]:
    """공백 제거·ID/Secret 뒤바뀴 자동 교정."""
    cid = _strip_credential(client_id)
    sec = _strip_credential(client_secret)
    notes: list[str] = []

    if cid and sec and _looks_like_client_secret(cid) and _looks_like_client_id(sec):
        cid, sec = sec, cid
        notes.append("CLIENT_ID ↔ SECRET 뒤바뀜 감지 — 자동 교정했습니다")

    if cid and not _looks_like_client_id(cid):
        if _looks_like_client_secret(cid):
            notes.append("CLIENT_ID 자리에 Secret(s_…) 값이 들어있습니다")
        elif len(cid) < 12:
            notes.append("CLIENT_ID 가 너무 짧습니다")
        else:
            notes.append("CLIENT_ID 형식 확인 (c_… 또는 tsck_… 로 시작)")

    if sec and not _looks_like_client_secret(sec):
        if _looks_like_client_id(sec):
            notes.append("SECRET 자리에 Client ID(c_/tsck_) 값이 들어있습니다")
        elif len(sec) < 20:
            notes.append("CLIENT_SECRET 이 너무 짧습니다")
        else:
            notes.append("CLIENT_SECRET 형식 확인 (s_… 로 시작)")

    return cid, sec, notes


def diagnose_toss_credentials(client_id: str, client_secret: str) -> dict:
    cid, sec, notes = normalize_toss_credentials(client_id, client_secret)
    return {
        "client_id_set": bool(cid),
        "client_secret_set": bool(sec),
        "client_id_masked": mask_credential(cid),
        "client_secret_masked": mask_credential(sec),
        "client_id_len": len(cid),
        "client_secret_len": len(sec),
        "id_format_ok": bool(cid) and _looks_like_client_id(cid),
        "secret_format_ok": bool(sec) and _looks_like_client_secret(sec),
        "notes": notes,
        "has_toss": bool(cid and sec),
    }


def format_toss_credential_help(*, auth_401: bool = False) -> list[str]:
    lines = [
        "WTS → 설정 → Open API → Client ID / Secret 재확인",
        "CLIENT_ID = c_… 또는 tsck_… (API Key)",
        "CLIENT_SECRET = s_… (Secret Key)",
        "한 줄씩: TOSS_CLIENT_ID=… / TOSS_CLIENT_SECRET=… (따옴표·공백 없이)",
        "VM .env 수정 후: sudo systemctl restart infinite-trading-bot",
    ]
    if auth_401:
        lines.insert(0, "401 = 키가 틀리거나 비활성·재발급 필요")
    return lines


_TOSS_INLINE_RE = re.compile(
    r"(TOSS_CLIENT_ID|TOSS_CLIENT_SECRET|TOSS_API_KEY|TOSS_SECRET_KEY|"
    r"TOSS_API_SECRET)\s*=\s*([^\s#]+)",
    re.IGNORECASE,
)

_TOSS_ID_ALIASES = ("TOSS_CLIENT_ID", "TOSS_API_KEY", "TOSS_API_ID", "TOSS_KEY")
_TOSS_SECRET_ALIASES = ("TOSS_CLIENT_SECRET", "TOSS_SECRET_KEY", "TOSS_API_SECRET", "TOSS_SECRET")


def toss_env_alias_conflicts(pairs: dict[str, str]) -> list[str]:
    """동일 역할 변수가 .env 에 중복·상충할 때 경고."""
    notes: list[str] = []

    def _vals(names: tuple[str, ...]) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in names:
            for k, v in pairs.items():
                if k.upper() == name and v:
                    out[name] = _strip_credential(v)
        return out

    id_vals = _vals(_TOSS_ID_ALIASES)
    if len(set(id_vals.values())) > 1:
        keys = ", ".join(sorted(id_vals))
        notes.append(f"Toss ID 변수 충돌 ({keys}) — TOSS_CLIENT_ID 만 남기고 정리")

    sec_vals = _vals(_TOSS_SECRET_ALIASES)
    if len(set(sec_vals.values())) > 1:
        keys = ", ".join(sorted(sec_vals))
        notes.append(f"Toss SECRET 변수 충돌 ({keys}) — TOSS_CLIENT_SECRET 만 남기고 정리")

    return notes
