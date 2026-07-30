"""Telegram — .env 인식 상태 (키 값은 마스킹)."""

from __future__ import annotations

from config.settings import ROOT, env_diagnostics, reload_settings
from tg.ui import code, quote, row, section


def format_env_check() -> str:
    settings = reload_settings()
    diag = env_diagnostics(settings)
    env_path = diag["env_path"]
    lines = [
        section("환경 설정 인식", "🔍"),
        quote(row("📄", ".env", code(env_path if diag["env_exists"] else "없음"))),
        "",
        section("거래·알림", "💹"),
        quote(
            row("Toss ID", _mark(diag["toss_client_id_set"])),
            row("Toss SECRET", _mark(diag["toss_client_secret_set"])),
            row("→ LIVE 가능", _mark(diag["has_toss"])),
            row("DRY_RUN", code(str(diag["dry_run"]).lower())),
            row("Telegram chat", _mark(diag["telegram_chat_ids_set"])),
        ),
        "",
        section("아침 브리핑 AI", "🌅"),
        quote(
            row("API 키", _mark(diag["summarizer_key_set"], diag.get("summarizer_key_from") or "")),
            row("BRIEFING", code("on" if diag["briefing_enabled"] else "off")),
        ),
        "",
        section("Google Sheets 장부", "📊"),
        quote(
            row("스프레드시트 ID", _mark(diag["spreadsheet_id_set"])),
            row("서비스계정 JSON", _mark(diag["service_account_set"], diag.get("service_account_path") or "")),
            row("→ Sheets OK", _mark(diag["has_google_sheets"])),
        ),
    ]
    if diag.get("notes"):
        lines.append("")
        lines.append(section("참고", "💡"))
        lines.append(quote(*[f"· {n}" for n in diag["notes"]]))
    if not diag["env_exists"]:
        lines.append("")
        lines.append(f"⚠️ VM 경로에 .env 없음: {ROOT / '.env'}")
    return "\n".join(lines)


def _mark(ok: bool, detail: str = "") -> str:
    badge = "✅" if ok else "❌"
    if detail:
        return code(f"{badge} {detail}")
    return code(badge)
