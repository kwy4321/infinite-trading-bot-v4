"""Telegram — .env 인식 상태 (키 값은 마스킹)."""

from __future__ import annotations

import html

from config.settings import ROOT, env_diagnostics, probe_llm_key_in_env_file, reload_settings, resolve_summarizer_api_key
from tg.build_info import git_rev
from tg.ui import code, quote, row, section


def format_env_check() -> str:
    settings = reload_settings()
    diag = env_diagnostics(settings)
    env_path = html.escape(diag["env_path"])
    sa_path = html.escape(diag.get("service_account_path") or "")
    summ_key, summ_src = resolve_summarizer_api_key(settings.summarizer_provider)
    summ_src = html.escape(summ_src)
    probe = probe_llm_key_in_env_file()
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
            row("🤖", "API 키", _mark(bool(summ_key), summ_src)),
            row("📄", ".env AI줄", _mark(probe.get("line_found", False), probe.get("line_name", ""))),
            row("🔤", "AIza 패턴", _mark(probe.get("aiza_in_file", False))),
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
    if diag.get("env_files_found"):
        found = ", ".join(html.escape(p) for p in diag["env_files_found"][:3])
        extra = len(diag["env_files_found"]) - 3
        if extra > 0:
            found += f" …(+{extra})"
        lines.insert(
            3,
            quote(row("📂", "env 파일", code(found))),
        )
    if diag.get("env_key_names"):
        names = ", ".join(html.escape(k) for k in diag["env_key_names"][:12])
        extra = len(diag["env_key_names"]) - 12
        if extra > 0:
            names += f" …(+{extra})"
        lines.append("")
        lines.append(section(".env 변수", "📝"))
        lines.append(quote(row("🔑", "로드됨", code(names or "없음"))))
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
