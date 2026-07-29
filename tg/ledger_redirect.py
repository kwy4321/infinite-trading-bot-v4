"""Streamlit / Google Sheets 장부 안내."""

from app import App
from tg.ui import code, dim, quote, row, section


def format_ledger_redirect(app: App, *, title: str = "장부·기록") -> str:
    settings = app.settings
    lines = [
        section(title, "📊"),
        quote(
            dim("텔레그램 장부 대신 Streamlit 대시보드와 Google Sheets를 사용합니다."),
            dim("매매·회차·월별 수익은 아래에서 확인하세요."),
        ),
        "",
    ]
    if settings.streamlit_url:
        lines.append(row("🖥️", "대시보드", code(settings.streamlit_url)))
    else:
        lines.append(row("🖥️", "대시보드", dim("STREAMLIT_URL 미설정")))
    if settings.has_google_sheets:
        url = settings.google_sheets_url or (
            f"https://docs.google.com/spreadsheets/d/{settings.google_spreadsheet_id}"
        )
        lines.append(row("📗", "Google Sheets", code(url)))
    else:
        lines.append(row("📗", "Google Sheets", dim("GOOGLE_SHEETS_ENABLED/ID/JSON 설정 필요")))
    lines.append("")
    lines.append(dim("/sheets_sync — Google Sheets 수동 동기화"))
    return "\n".join(lines)
