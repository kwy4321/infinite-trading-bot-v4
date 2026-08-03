"""모든 모듈이 실제로 import 되는지 — 리팩터링 중 남은 참조를 잡는다.

compileall 은 문법만 본다. 옮긴 함수의 import 를 빼먹으면 여기서 걸린다.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {"scripts", "tests", "deploy", "data", "__pycache__", ".git", ".venv", "venv"}

#: streamlit 런타임 밖에서 import 하면 부작용이 있는 모듈
SKIP_MODULES = {"dashboard.streamlit_app"}


def _module_names() -> list[str]:
    names: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if rel.name == "__init__.py":
            parts = rel.parts[:-1]
            if not parts:
                continue
            name = ".".join(parts)
        else:
            name = ".".join(rel.with_suffix("").parts)
        if name in SKIP_MODULES:
            continue
        names.append(name)
    return names


@pytest.mark.parametrize("module_name", _module_names())
def test_module_imports(module_name):
    importlib.import_module(module_name)
