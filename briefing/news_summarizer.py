from config.settings import Settings


async def summarize_news(settings: Settings) -> str:
    if settings.summarizer_api_key or settings.news_api_key:
        return "💡 <b>뉴스 요약</b>\n· API 키 설정됨 — 추후 연동"
    return "💡 <b>뉴스 요약</b>\n· NEWS_API_KEY / SUMMARIZER_API_KEY 설정 시 활성화"
