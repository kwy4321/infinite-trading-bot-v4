"""Telegram — .env 인식 상태 (키 값은 마스킹)."""

from __future__ import annotations

import html

from config.settings import ROOT, env_diagnostics, reload_settings
from tg.build_info import git_rev
from tg.ui import code, quote, row, section


def format_env_check() -> str:
    settings = reload_settings()
    diag = env_diagnostics(settings)
    env_path = html.escape(diag["env_path"])
    sa_path = html.escape(diag.get("service_account_path") or "")
    summ_src = html.escape(diag.get("summarizer_key_from") or "")
    lines = [
        section("환경 설정 인식", "🔍"),
        quote(
            row("📄", ".env", code(env_path if diag["env_exists"] else "없음")),
            row("🔖", "빌드", code(git_rev())),
        ),
        "",
        section("거래·알림", "💹"),
        quote(
            row("🔑", "Toss ID", _mark(diag["toss_client_id_set"])),
            row("🔑", "Toss SECRET", _mark(diag["toss_client_secret_set"])),
            row("💹", "LIVE 가능", _mark(diag["has_toss"])),
            row("🧪", "DRY_RUN", code(str(diag["dry_run"]).lower())),
            row("💬", "Telegram chat", _mark(diag["telegram_chat_ids_set"])),
        ),
        "",
        section("아침 브리핑 AI", "🌅"),
        quote(
            row("🤖", "API 키", _mark(diag["summarizer_key_set"], summ_src)),
            row("⏰", "BRIEFING", code("on" if diag["briefing_enabled"] else "off")),
        ),
        "",
        section("Google Sheets 장부", "📊"),
        quote(
            row("📋", "스프레드시트 ID", _mark(diag["spreadsheet_id_set"])),
            row("📁", "서비스계정 JSON", _mark(diag["service_account_set"], sa_path)),
            row("✅", "Sheets OK", _mark(diag["has_google_sheets"])),
        ),
    ]
    if diag.get("notes"):
        lines.append("")
        lines.append(section("참고", "💡"))
        lines.append(quote(*[f"· {html.escape(n)}" for n in diag["notes"]]))
    if not diag["env_exists"]:
        lines.append("")
        lines.append(f"⚠️ VM 경로에 .env 없음: {html.escape(str(ROOT / '.env'))}")
    return "\n".join(lines)


def _mark(ok: bool, detail: str = "") -> str:
    badge = "✅" if ok else "❌"
    if detail:
        return code(f"{badge} {detail}")
    return code(badge)
