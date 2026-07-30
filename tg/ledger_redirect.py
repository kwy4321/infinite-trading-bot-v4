"""Google Sheets 장부 안내."""

from __future__ import annotations

from app import App
from config.settings import google_sheets_issues
from tg.ui import code, dim, quote, row, section


def format_ledger_redirect(app: App, *, title: str = "장부") -> str:
    settings = app.settings
    issues = google_sheets_issues(settings)
    hints = [dim("아래 버튼으로 Google Sheets를 열 수 있습니다.")]
    if not issues:
        hints.append(dim("장부 메뉴를 열면 Google Sheets에 자동 동기화됩니다."))
    lines = [f"{section(title, '📊')}", quote(*hints), ""]
    if not issues and settings.google_sheets_link:
        lines.append(row("📗", "Sheets", code(settings.google_sheets_link)))
    elif issues:
        lines.append(row("⚠️", "설정", dim(" · ".join(issues))))
        lines.append(
            row("💡", "안내", dim("Cloud Shell .env + data/google-service-account.json → bash scripts/cloudshell_bot.sh start")),
        )
    return "\n".join(lines)
