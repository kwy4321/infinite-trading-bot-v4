"""텔레그램 HTML 안전 조립.

텔레그램 parse_mode=HTML 의 제약을 이 모듈이 전부 흡수한다.
  1. 사용자/API 유래 텍스트는 항상 escape → `&`, `<` 때문에 전송이 실패하지 않는다.
  2. blockquote 는 중첩 불가 → quote() 가 본문의 blockquote 를 자동으로 제거한다.
  3. 메시지 4096자 제한 → split_html() 이 태그를 깨지 않고 나눈다.

이전에 /plan 이 "조회 중..." 에서 멈춘 원인이 2번(중첩 blockquote)이었다.
포맷터마다 직접 f"<blockquote>..." 를 쓰지 말고 반드시 이 함수들을 쓴다.
"""

from __future__ import annotations

import html as _html
import re

DIVIDER = "━━━━━━━━━━━━━━━━"
THIN = "┈┈┈┈┈┈┈┈┈┈┈┈"
DOTS = "· · · · · · · · · · · ·"

#: 텔레그램 sendMessage 본문 길이 제한
TELEGRAM_MAX_LEN = 4096

#: 텔레그램이 허용하는 태그 (그 외는 전송 실패 원인)
ALLOWED_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "blockquote", "span", "tg-spoiler", "tg-emoji",
})

#: blockquote 안에 들어갈 수 없는 블록 태그
BLOCK_TAGS = frozenset({"blockquote", "pre"})

_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?/?>")
_BLOCKQUOTE_RE = re.compile(r"</?blockquote(\s[^>]*)?>", re.IGNORECASE)
_VOID_TAGS = frozenset({"br", "hr", "img"})


def esc(text: object) -> str:
    """모든 동적 텍스트의 기본 진입점 — & < > 를 엔티티로 변환."""
    return _html.escape(str(text if text is not None else ""), quote=False)


def _join(lines) -> str:
    return "\n".join(str(line) for line in lines if line is not None)


def strip_tags(text: str) -> str:
    """HTML 제거 + 엔티티 복원 — 전송 실패 시 plain text fallback 용."""
    return _html.unescape(_TAG_RE.sub("", str(text or "")))


def unquote_body(text: str) -> str:
    """중첩 방지 — 본문에 이미 있는 blockquote 태그를 제거한다."""
    return _BLOCKQUOTE_RE.sub("", str(text or ""))


def quote(*lines) -> str:
    """카드처럼 보이는 인용 박스. 본문의 blockquote 는 자동 제거된다."""
    return f"<blockquote>{unquote_body(_join(lines))}</blockquote>"


def quote_exp(*lines) -> str:
    """접을 수 있는 인용 박스 — 긴 목록(기록 등)에 사용."""
    return f"<blockquote expandable>{unquote_body(_join(lines))}</blockquote>"


def card(*lines) -> str:
    """blockquote 없는 카드 — 여러 카드를 이어 붙일 때(주문계획 등) 사용."""
    return f"{_join(lines)}\n{THIN}"


def code(text: object) -> str:
    """숫자·값 강조. blockquote 안에서는 <code> 대신 bold 를 쓴다."""
    return f"<b>{esc(text)}</b>"


def bold(text: object) -> str:
    return f"<b>{esc(text)}</b>"


def dim(text: object) -> str:
    return f"<i>{esc(text)}</i>"


def validate_html(text: str) -> list[str]:
    """텔레그램 HTML 위반 목록. 비어 있으면 안전. (테스트·개발용)"""
    problems: list[str] = []
    stack: list[str] = []
    for match in _TAG_RE.finditer(text or ""):
        raw = match.group(0)
        name = match.group(1).lower()
        if name in _VOID_TAGS or raw.endswith("/>"):
            problems.append(f"void tag not supported: {raw}")
            continue
        if name not in ALLOWED_TAGS:
            problems.append(f"tag not allowed by Telegram: <{name}>")
            continue
        if raw.startswith("</"):
            if not stack:
                problems.append(f"unmatched closing </{name}>")
            elif stack[-1] != name:
                problems.append(f"tag order mismatch: </{name}> closes <{stack[-1]}>")
                stack.pop()
            else:
                stack.pop()
            continue
        if name in BLOCK_TAGS and any(t in BLOCK_TAGS for t in stack):
            problems.append(f"nested block tag <{name}> inside <{stack[-1]}>")
        stack.append(name)
    for name in reversed(stack):
        problems.append(f"unclosed <{name}>")
    return problems


def _open_tags_at_end(text: str) -> list[tuple[str, str]]:
    """조각 끝에서 아직 닫히지 않은 태그 — (태그명, 여는 태그 원문)."""
    stack: list[tuple[str, str]] = []
    for match in _TAG_RE.finditer(text):
        name = match.group(1).lower()
        if name not in ALLOWED_TAGS:
            continue
        if match.group(0).startswith("</"):
            if stack and stack[-1][0] == name:
                stack.pop()
        else:
            stack.append((name, match.group(0)))
    return stack


def _cut_point(text: str, limit: int) -> int:
    """limit 이하에서 태그 내부를 쪼개지 않는 안전한 절단 위치."""
    hard = limit
    window = text[:hard]
    if window.rfind("<") > window.rfind(">"):
        hard = window.rfind("<")
        window = text[:hard]
    for sep in ("\n\n", "\n", " "):
        idx = window.rfind(sep)
        if idx > hard // 2:
            return idx + len(sep)
    return max(hard, 1)


def split_html(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """긴 HTML 메시지를 태그 균형을 유지한 채 여러 조각으로 나눈다.

    조각 끝에서 열려 있는 태그는 닫고, 다음 조각 머리에서 다시 연다.
    닫는 태그를 붙여도 limit 을 넘지 않도록 절단 위치를 되돌려 잡는다.
    """
    body = str(text or "")
    if len(body) <= limit:
        return [body] if body else [""]

    chunks: list[str] = []
    rest = body
    floor = max(1, limit // 2)
    while len(rest) > limit:
        budget = limit
        for _ in range(4):
            cut = _cut_point(rest, budget)
            head = rest[:cut].rstrip()
            pending = _open_tags_at_end(head)
            closing = "".join(f"</{name}>" for name, _ in reversed(pending))
            if len(head) + len(closing) <= limit:
                break
            budget = max(floor, budget - len(closing) - 1)
        reopen = "".join(raw for _, raw in pending)
        tail = reopen + rest[cut:]
        if len(tail) >= len(rest):  # 진전이 없으면 그대로 잘라 무한 루프를 막는다
            chunks.append(rest[:limit])
            rest = rest[limit:]
            continue
        chunks.append(head + closing)
        rest = tail
    if rest.strip():
        chunks.append(rest)
    return chunks
