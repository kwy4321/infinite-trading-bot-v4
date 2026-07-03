"""아침 뉴스 요약.

1) 무료 Google News RSS(한국어) 로 나스닥·반도체 관련 헤드라인을 수집한다(키 불필요).
2) SUMMARIZER_API_KEY 가 있으면 LLM(Gemini/OpenAI)으로 나스닥·반도체 각각
   "왜 움직였는지"를 한국어로 요약한다. 키가 없으면 헤드라인 목록만 보여준다.

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
    "나스닥 지수",
    "반도체 엔비디아 주가",
)
_MAX_PER_QUERY = 4
_MAX_TOTAL = 8

# 마커로 두 파트를 구분 → 각각 별도 카드로 렌더링
_MARK_NASDAQ = "[나스닥]"
_MARK_SEMI = "[반도체]"
_PROMPT_TRADING = (
    "다음은 미국 증시·반도체 관련 한국어 뉴스 헤드라인입니다.\n"
    "나스닥 종합지수와 필라델피아 반도체지수(SOX)가 {session_label} 미국장에서 "
    "왜 그렇게 움직였는지 한국어로 분석하세요.\n"
    "반드시 아래 형식을 그대로 지키고, 다른 머리말이나 설명은 넣지 마세요:\n"
    f"{_MARK_NASDAQ}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n"
    f"{_MARK_SEMI}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n"
    "각 지수마다 구체적인 불릿 3개를 쓰고, 금리·경제지표·실적·개별 종목 등 "
    "원인을 분명히 밝히세요. 헤드라인에 없는 사실은 추측하지 마세요.\n\n"
    "헤드라인:\n"
)
_PROMPT_HOLIDAY = (
    "다음은 미국 증시·반도체 관련 한국어 뉴스 헤드라인입니다.\n"
    "⚠️ {holiday_label} 미국 정규장은 휴장이었습니다. "
    "지수는 전 거래일 {session_label} 마감 기준입니다.\n"
    "오늘 장이 열리지 않았다는 점을 첫 불릿에 명시하고, "
    "헤드라인에 근거한 시장 배경·전망만 정리하세요. "
    "휴장일에 지수가 올랐다/내렸다고 쓰지 마세요.\n"
    "반드시 아래 형식:\n"
    f"{_MARK_NASDAQ}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n"
    f"{_MARK_SEMI}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n\n"
    "헤드라인:\n"
)


def _has_korean(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def _fetch_headlines() -> list[dict]:
    collected: list[dict] = []
    seen: set[str] = set()
    for query in _QUERIES:
        try:
            resp = requests.get(
                _RSS,
                params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
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
            # 영어 헤드라인 제외 — 한글이 포함된 기사만
            if not _has_korean(title):
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


def _split_sections(text: str) -> tuple[str, str] | None:
    """AI 응답을 [나스닥]/[반도체] 두 파트로 분리. 실패 시 None."""
    cleaned = text.replace("**", "").replace("`", "")
    n_idx = cleaned.find(_MARK_NASDAQ)
    s_idx = cleaned.find(_MARK_SEMI)
    if n_idx == -1 or s_idx == -1 or s_idx <= n_idx:
        return None
    nasdaq = cleaned[n_idx + len(_MARK_NASDAQ):s_idx].strip()
    semi = cleaned[s_idx + len(_MARK_SEMI):].strip()
    if not nasdaq or not semi:
        return None
    return nasdaq, semi


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


def _build_sync(settings: Settings, market_ctx: dict | None = None) -> str:
    items = _fetch_headlines()
    parts: list[str] = []
    ctx = market_ctx or {}

    api_key = settings.summarizer_api_key
    if api_key and items:
        headlines_text = "\n".join(
            f"- {item['title']} ({item['source']})" for item in items
        )
        if ctx.get("us_holiday"):
            prompt = _PROMPT_HOLIDAY.format(
                holiday_label=ctx.get("holiday_label") or "해당일",
                session_label=ctx.get("session_label") or "전 거래일",
            ) + headlines_text
        else:
            prompt = _PROMPT_TRADING.format(
                session_label=ctx.get("session_label") or "전일",
            ) + headlines_text
        provider = (settings.summarizer_provider or "openai").lower()
        if provider == "gemini":
            summary = _summarize_gemini(api_key, settings.summarizer_model, prompt)
        else:
            summary = _summarize_openai(api_key, settings.summarizer_model, prompt)
        if summary:
            split = _split_sections(summary)
            if split:
                nasdaq, semi = split
                parts.append(
                    f"{section('나스닥 종합 · AI 분석', '📊')}\n{quote(html.escape(nasdaq))}"
                )
                parts.append(
                    f"{section('필라델피아 반도체 · AI 분석', '🔌')}\n{quote(html.escape(semi))}"
                )
            else:
                parts.append(
                    f"{section('왜 움직였나 · AI 요약', '💡')}\n{quote(_clean_summary(summary))}"
                )

    parts.append(_format_headlines(items))
    return "\n\n".join(parts)


async def summarize_news(
    settings: Settings, *, market_ctx: dict | None = None,
) -> str:
    return await asyncio.to_thread(_build_sync, settings, market_ctx)
