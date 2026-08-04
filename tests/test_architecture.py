"""계층 규칙 가드 — 기능 추가로 구조가 다시 뒤틀리는 것을 막는다.

여기서 실패하면 "동작은 하지만 구조가 무너지는" 변경이다.
새 모듈을 추가하면 아래 LAYERS 에 등록해야 한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 계층 번호 — 낮은 계층은 높은 계층을 import 할 수 없다.
LAYERS: dict[str, int] = {
    "core": 0,
    "config": 1,
    "account": 1,
    "render": 1,
    "broker": 2,
    "state": 2,
    "strategy": 3,
    "cycles": 3,
    "app": 4,
    "services": 5,
    "reporting": 5,
    # 표현·오케스트레이션은 같은 층 — tg 핸들러가 executor 를, executor 가
    # 알림 포맷터를 쓰는 양방향 참조가 정상이기 때문이다.
    "tg": 6,
    "briefing": 6,
    "dashboard": 6,
    "integrations": 6,
    "jobs": 6,
    "main": 7,
}

#: 도메인 계층 — 표현/전송 계층을 절대 참조하지 않는다.
PRESENTATION = {"tg", "dashboard", "briefing", "integrations", "jobs", "main"}

#: 검사 제외 — 운영 스크립트와 테스트는 어디든 import 할 수 있다.
SKIP_DIRS = {"scripts", "tests", "deploy", "data", ".git", "__pycache__", ".venv", "venv"}

#: render 는 순수 포맷 라이브러리 — 상태를 가진 모듈을 참조하면 안 된다.
RENDER_FORBIDDEN = {"app", "broker", "state", "cycles", "strategy", "services", "reporting"}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def _module_name(path: Path) -> str:
    """파일 경로 → 소속 최상위 모듈명 (core/clock.py → core)."""
    rel = path.relative_to(ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def _is_type_checking_test(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    return False


def _type_checking_lines(tree: ast.AST) -> set[int]:
    """`if TYPE_CHECKING:` 블록의 줄 번호 — 타입 전용 import 는 런타임 결합이 아니다."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for stmt in node.body:
                end = getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno
                lines.update(range(stmt.lineno, end + 1))
    return lines


def _internal_imports(path: Path) -> set[tuple[str, int]]:
    """(최상위 모듈명, 줄번호) — 프로젝트 내부 런타임 import 만."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    type_only = _type_checking_lines(tree)
    found: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 상대 import
                continue
            names = [node.module or ""]
        else:
            continue
        if node.lineno in type_only:
            continue
        for name in names:
            top = name.split(".")[0]
            if top in LAYERS:
                found.add((top, node.lineno))
    return found


def _violations(predicate) -> list[str]:
    problems: list[str] = []
    for path in _python_files():
        owner = _module_name(path)
        if owner not in LAYERS:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for imported, lineno in sorted(_internal_imports(path)):
            if imported == owner:
                continue
            message = predicate(owner, imported)
            if message:
                problems.append(f"{rel}:{lineno} {message}")
    return problems


def test_layers_do_not_import_upward():
    """낮은 계층이 높은 계층을 import 하지 않는다."""

    def check(owner: str, imported: str) -> str | None:
        if LAYERS[imported] > LAYERS[owner]:
            return (
                f"{owner}(L{LAYERS[owner]}) → {imported}(L{LAYERS[imported]}) "
                "역방향 의존"
            )
        return None

    problems = _violations(check)
    assert not problems, "계층 역방향 의존:\n" + "\n".join(problems)


def test_domain_never_imports_presentation():
    """전략·회차·브로커 같은 도메인이 텔레그램/대시보드를 참조하지 않는다."""

    def check(owner: str, imported: str) -> str | None:
        if owner not in PRESENTATION and imported in PRESENTATION:
            return f"도메인 {owner} 가 표현 계층 {imported} 을 참조"
        return None

    problems = _violations(check)
    assert not problems, (
        "도메인 → 표현 계층 의존 (services/render 를 쓰세요):\n" + "\n".join(problems)
    )


def test_core_is_dependency_free():
    """core 는 프로젝트 내부의 다른 어떤 것도 import 하지 않는다."""

    def check(owner: str, imported: str) -> str | None:
        if owner == "core":
            return f"core 가 {imported} 를 참조 (core 는 순수 유틸이어야 함)"
        return None

    problems = _violations(check)
    assert not problems, "core 순수성 위반:\n" + "\n".join(problems)


def test_render_is_pure_formatting():
    """render 는 app/broker/state 등 상태 모듈을 참조하지 않는다."""

    def check(owner: str, imported: str) -> str | None:
        if owner == "render" and imported in RENDER_FORBIDDEN:
            return f"render 가 {imported} 를 참조 (render 는 순수 포맷 계층)"
        return None

    problems = _violations(check)
    assert not problems, "render 순수성 위반:\n" + "\n".join(problems)


def test_timezone_declared_only_in_core_clock():
    """KST/NY 타임존 선언은 core/clock.py 한 곳만 — 날짜 버그 재발 방지."""
    offenders: list[str] = []
    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "core/clock.py":
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "ZoneInfo(" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{rel}:{lineno} {line.strip()}")
    assert not offenders, (
        "ZoneInfo 직접 선언 금지 — core.clock 의 KST/NY 를 import 하세요:\n"
        + "\n".join(offenders)
    )


def test_no_duplicate_money_parser():
    """금액 파싱 구현은 core/money.py 한 곳만."""
    offenders: list[str] = []
    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "core/money.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {
                "_money", "cash_usd", "cash_krw", "parse_money",
            }:
                offenders.append(f"{rel}:{node.lineno} def {node.name}")
    assert not offenders, (
        "금액 파싱 중복 정의 — core.money 를 import 하세요:\n" + "\n".join(offenders)
    )


def test_run_for_symbol_is_dry_before_holdings_qty():
    """18:05 LOC — resolve_holdings_qty 호출 전 is_dry 가 정의돼야 한다 (UnboundLocalError 방지)."""
    text = (ROOT / "jobs" / "executor.py").read_text(encoding="utf-8")
    start = text.index("async def run_for_symbol")
    end = text.index("\n    def _target_us_date_for_phase", start)
    body = text[start:end]
    assert body.index("is_dry = self._is_dry()") < body.index("resolve_holdings_qty")
