"""async 함수 안에서 브로커 HTTP 를 직접 호출하지 않는지 검사.

이벤트 루프에서 requests 를 돌리면 봇 전체가 멈춘다 (/plan "조회 중..." 사건).
반드시 asyncio.to_thread(...) 로 감싸야 한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: HTTP 를 타는 브로커/외부 호출 — async 본문에서 직접 호출 금지
BLOCKING_CALLS = {
    "get_holdings_overview",
    "get_holdings_item",
    "get_price",
    "get_buying_power",
    "get_exchange_rate",
    "get_us_market_calendar",
    "get_us_market_status",
    "check_us_regular_session",
    "is_us_loc_session_now",
    "is_us_regular_session_now",
    "is_us_market_open_today",
    "list_broker_fills",
    "cancel_open_cls_orders",
    "fetch_public_ip",
}

#: 검사 대상 — 실제로 asyncio 루프를 돌리는 패키지
SCAN_DIRS = ("tg", "jobs", "briefing")


def _async_bodies(tree: ast.AST) -> list[ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def _to_thread_arg_nodes(func: ast.AST) -> set[int]:
    """asyncio.to_thread(...) 의 인자로 전달된 노드 id — 호출이 아니라 참조다."""
    safe: set[int] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name not in {"to_thread", "run_in_executor"}:
            continue
        for arg in node.args:
            safe.update(id(sub) for sub in ast.walk(arg))
    return safe


def _direct_blocking_calls(func: ast.AsyncFunctionDef) -> list[tuple[str, int]]:
    safe_nodes = _to_thread_arg_nodes(func)
    nested = {
        id(n) for child in ast.walk(func)
        if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)) and child is not func
        for n in ast.walk(child)
    }
    found: list[tuple[str, int]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call) or id(node) in safe_nodes or id(node) in nested:
            continue
        target = node.func
        if not isinstance(target, ast.Attribute):
            continue
        if target.attr in BLOCKING_CALLS:
            found.append((target.attr, node.lineno))
    return found


def test_no_blocking_broker_call_in_async_functions():
    offenders: list[str] = []
    for folder in SCAN_DIRS:
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel = path.relative_to(ROOT).as_posix()
            for func in _async_bodies(tree):
                for name, lineno in _direct_blocking_calls(func):
                    offenders.append(f"{rel}:{lineno} {func.name}() → {name}()")
    assert not offenders, (
        "async 안에서 블로킹 호출 — asyncio.to_thread 로 감싸세요:\n"
        + "\n".join(sorted(offenders))
    )
