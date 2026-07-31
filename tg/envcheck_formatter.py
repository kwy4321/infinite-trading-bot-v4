"""Telegram — .env 인식 상태 (키 값은 마스킹)."""

from __future__ import annotations

import html

from config.settings import ROOT, Settings, env_diagnostics, probe_llm_key_in_env_file, resolve_summarizer_api_key
from tg.build_info import git_rev
from tg.ui import code, quote, row, section


def format_env_check(settings: Settings) -> str:
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
            row("🌐", "서버 IP", code(diag.get("public_ip") or "—")),
            row("🔑", "Toss ID", _toss_mark(diag)),
            row("🔑", "Toss SECRET", _toss_secret_mark(diag)),
            row("💹", "LIVE 가능", _mark(diag["has_toss"])),
            row("🧪", "DRY_RUN", code(str(diag["dry_run"]).lower())),
            row("💬", "Telegram chat", _mark(diag["telegram_chat_ids_set"])),
        ),
        "",
        section("아침 브리핑 AI", "🌅"),
        quote(
            row("🤖", "API 키", _mark(bool(summ_key), summ_src)),
            row("📄", ".env AI줄", _mark(probe.get("line_found", False), probe.get("line_name", ""))),
            row("📁", "gemini.txt", _mark(probe.get("gemini_txt_ok", False))),
            row("🔤", "키 형식", code(_format_mark(probe))),
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
    if not summ_key:
        lines.append("")
        lines.append(section("AI 키 해결", "🛠"))
        if probe.get("wrong_format"):
            lines.append(quote(
                "· 지금 키는 Gemini API 키가 아닙니다 (AQ.Ab… = OAuth/토큰)",
                "· https://aistudio.google.com/app/apikey 에서 AIza… 키 발급",
                "· Cloud Shell: bash scripts/set_vm_api_key.sh",
            ))
        elif probe.get("gemini_txt_ok"):
            lines.append(quote("· gemini.txt 있음 — restart 후에도 ❌면 빌드 e728275+ 확인"))
        elif not probe.get("line_found") and not probe.get("aiza_in_file"):
            lines.append(quote(
                "· VM .env에 SUMMARIZER_API_KEY 없음",
                "· Cloud Shell: bash scripts/set_vm_api_key.sh",
            ))
        elif probe.get("line_found") and not probe.get("parsed_ok"):
            lines.append(quote(
                "· 줄은 있으나 값 비어있음 — set_vm_api_key.sh 로 다시 입력",
            ))
        else:
            lines.append(quote(
                "· bash scripts/cloudshell_bot.sh restart",
                "· 또는 data/gemini_api_key.txt 에 AIza키 한 줄",
            ))
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


def _toss_mark(diag: dict) -> str:
    if not diag.get("toss_client_id_set"):
        return code("❌")
    masked = diag.get("toss_client_id_masked") or ""
    fmt = diag.get("toss_id_format_ok")
    badge = "✅" if fmt else "⚠️"
    return code(f"{badge} {masked}")


def _toss_secret_mark(diag: dict) -> str:
    if not diag.get("toss_client_secret_set"):
        return code("❌")
    masked = diag.get("toss_client_secret_masked") or ""
    fmt = diag.get("toss_secret_format_ok")
    badge = "✅" if fmt else "⚠️"
    return code(f"{badge} {masked}")


def _format_mark(probe: dict) -> str:
    if probe.get("valid_set"):
        return "✅ AIza…"
    if probe.get("wrong_format"):
        return f"❌ {probe.get('key_format', '형식 오류')}"
    if probe.get("raw_set"):
        return f"❌ {probe.get('key_format', '형식 오류')}"
    if probe.get("aiza_in_file"):
        return "⚠️ AIza 있으나 파싱 실패"
    return "❌ AIza… 없음"
