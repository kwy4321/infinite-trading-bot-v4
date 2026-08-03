"""거래 가능 종목 유니버스 단일 소스.

용어 구분 — 이걸 섞어 쓰다가 대시보드에 미거래 종목이 노출되는 버그가 있었다.
  * UNIVERSE (=SYMBOLS): 봇이 지원하는 전체 종목. 저장·백업·선택 UI 용도.
  * active symbols: 지금 실제로 매매 중인 종목. 조회·표시·주문은 반드시 이것 기준.
"""

from __future__ import annotations

#: 봇이 지원하는 전체 종목 (저장/백업/선택 UI 기준)
SYMBOL_UNIVERSE: tuple[str, ...] = ("TQQQ", "SOXL")

#: 하위 호환 별칭 — config.settings.SYMBOLS 가 이걸 재노출한다.
SYMBOLS = SYMBOL_UNIVERSE

DEFAULT_ACTIVE_SYMBOLS: tuple[str, ...] = ("TQQQ",)


def normalize_symbol(symbol: object) -> str:
    return str(symbol or "").strip().upper()


def is_known(symbol: object) -> bool:
    return normalize_symbol(symbol) in SYMBOL_UNIVERSE


def normalize_symbols(symbols: object) -> list[str]:
    """입력 목록 → 유니버스에 속하는 대문자 종목, 순서 유지·중복 제거."""
    if not symbols:
        return []
    if isinstance(symbols, str):
        raw = [part for part in symbols.replace(",", " ").split() if part]
    else:
        raw = list(symbols)
    out: list[str] = []
    for item in raw:
        sym = normalize_symbol(item)
        if sym in SYMBOL_UNIVERSE and sym not in out:
            out.append(sym)
    return out
