"""Morning briefing assembler."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from briefing.index_fetcher import fetch_index_summary
from briefing.news_summarizer import summarize_news


async def build_briefing(app: App) -> str:
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
    lines = [f"🌅 <b>아침 브리핑</b> ({now} KST)\n"]
    for sym in app.state.list_symbols():
        st = app.state.load(sym)
        lines.append(f"📦 <b>{sym}</b> T={st['T']:.2f} | {st['qty']}주 @ ${st['avg_price']:.2f}")
    lines.append("")
    lines.append(await fetch_index_summary())
    lines.append("")
    lines.append(await summarize_news(app.settings))
    return "\n".join(lines)
