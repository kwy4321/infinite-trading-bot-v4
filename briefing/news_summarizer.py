"""아침 뉴스 요약.

1) 무료 Google News RSS 로 나스닥·반도체 관련 헤드라인을 수집한다(키 불필요).
2) SUMMARIZER_API_KEY 가 있으면 LLM(OpenAI/Gemini)으로 "왜 움직였는지"를
   한국어로 요약한다. 키가 없으면 헤드라인 목록만 보여준다.

requests 는 블로킹이라 asyncio.to_thread 로 감싼다.
"""

import asyncio
import html
import logging
import xml.etree.ElementTree as ET

import requests

from config.settings import Settings
from tg.ui import dim, quote, section

logger = logging.getLogger(__name__)

_RSS = "https://news.google.com/rss/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (infinite-trading-bot briefing)"}
_QUERIES = (
    "nasdaq stock market today",
    "semiconductor stocks nvidia chip",
)
_MAX_PER_QUERY = 4
_MAX_TOTAL = 8

_PROMPT = (
    "다음은 오늘 미국 증시·반도체 관련 뉴스 헤드라인입니다. "
    "나스닥 종합지수와 필라델피아 반도체지수(SOX)가 왜 그렇게 움직였는지 "
    "핵심 이유를 한국어로 3~4개의 짧은 불릿(각 한 문장)으로 요약하세요. "
    "헤드라인에 없는 내용은 추측하지 말고, 불릿마다 앞에 '· ' 를 붙이세요.\n\n"
)


def _fetch_headlines() -> list[dict]:
    collected: list[dict] = []
    seen: set[str] = set()
    for query in _QUERIES:
        try:
            resp = requests.get(
                _RSS,
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            logger.warning("뉴스 RSS 실패 %s: %s", query, exc)
            continue
        count = 0
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            src_el = item.find("source")
            source = (src_el.text or "").strip() if src_el is not None else ""
            collected.append({"title": title, "source": source})
            count += 1
            if count >= _MAX_PER_QUERY or len(collected) >= _MAX_TOTAL:
                break
        if len(collected) >= _MAX_TOTAL:
            break
    return collected


def _summarize_openai(api_key: str, model: str, prompt: str) -> str | None:
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("OpenAI 요약 실패: %s", exc)
        return None


def _summarize_gemini(api_key: str, model: str, prompt: str) -> str | None:
    model = model or "gemini-2.5-flash"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:
        logger.warning("Gemini 요약 실패: %s", exc)
        return None


def _clean_summary(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return html.escape(text.strip())


def _format_headlines(items: list[dict]) -> str:
    if not items:
        return f"{section('주요 뉴스', '📰')}\n{quote('· 뉴스를 불러오지 못했습니다')}"
    rows = []
    for item in items:
        title = html.escape(item["title"])
        source = item["source"]
        suffix = dim(f" · {html.escape(source)}") if source else ""
        rows.append(f"· {title}{suffix}")
    return f"{section('주요 뉴스', '📰')}\n{quote(*rows)}"


def _build_sync(settings: Settings) -> str:
    items = _fetch_headlines()
    parts: list[str] = []

    api_key = settings.summarizer_api_key
    if api_key and items:
        headlines_text = "\n".join(
            f"- {item['title']} ({item['source']})" for item in items
        )
        prompt = _PROMPT + headlines_text
        provider = (settings.summarizer_provider or "openai").lower()
        if provider == "gemini":
            summary = _summarize_gemini(api_key, settings.summarizer_model, prompt)
        else:
            summary = _summarize_openai(api_key, settings.summarizer_model, prompt)
        if summary:
            parts.append(
                f"{section('왜 움직였나 · AI 요약', '💡')}\n{quote(_clean_summary(summary))}"
            )

    parts.append(_format_headlines(items))
    return "\n\n".join(parts)


async def summarize_news(settings: Settings) -> str:
    return await asyncio.to_thread(_build_sync, settings)
