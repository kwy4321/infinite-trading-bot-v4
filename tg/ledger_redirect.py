"""Streamlit / Google Sheets 장부 안내."""

from app import App
from tg.ui import code, dim, quote, row, section


def format_ledger_redirect(app: App, *, title: str = "장부") -> str:
    settings = app.settings
    hints = [dim("아래 버튼으로 Streamlit · Google Sheets를 열 수 있습니다.")]
    if settings.has_google_sheets:
        hints.append(dim("장부 메뉴를 열면 Google Sheets에 자동 동기화됩니다."))
    lines = [f"{section(title, '📊')}", quote(*hints), ""]
    if settings.streamlit_link:
        lines.append(row("🖥️", "Streamlit", code(settings.streamlit_link)))
    else:
        lines.append(row("🖥️", "Streamlit", dim("STREAMLIT_URL 미설정 (.env 확인 후 봇 재시작)")))
    if settings.has_google_sheets and settings.google_sheets_link:
        lines.append(row("📗", "Sheets", code(settings.google_sheets_link)))
    elif not settings.has_google_sheets:
        lines.append(row("📗", "Sheets", dim("GOOGLE_SHEETS_* 미설정")))
    return "\n".join(lines)
