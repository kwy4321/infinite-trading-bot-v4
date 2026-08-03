"""금액·수익률·행 조립 — HTML 은 render.html 을 통해서만 만든다."""

from __future__ import annotations

from render.html import DIVIDER, bold, code, dim, esc
from render.labels import trend_arrow


def usd(amount: float, decimals: int = 2, signed: bool = False) -> str:
    sign = "+" if signed and amount > 0 else ""
    return code(f"{sign}${amount:,.{decimals}f}")


def krw(amount: float, signed: bool = False) -> str:
    sign = "+" if signed and amount > 0 else ""
    return code(f"{sign}₩{amount:,.0f}")


def pct(value: float, signed: bool = True) -> str:
    sign = "+" if value > 0 else ""
    if not signed and value <= 0:
        sign = ""
    return dim(f"({sign}{value:.1f}%)")


def pnl_line(amount_usd: float, pct_val: float) -> str:
    sign = "+" if amount_usd >= 0 else ""
    return f"{trend_arrow(amount_usd >= 0)} {code(f'{sign}${amount_usd:,.0f}')}  {pct(pct_val)}"


def pnl_line_precise(amount_usd: float, pct_val: float) -> str:
    sign = "+" if amount_usd >= 0 else ""
    return f"{trend_arrow(amount_usd >= 0)} {code(f'{sign}${amount_usd:,.2f}')}  {pct(pct_val)}"


def pnl_line_brief(amount_usd: float, pct_val: float) -> str:
    """pnl_line 별칭 (브리핑·호환)."""
    return pnl_line(amount_usd, pct_val)


def section(title: str, emoji: str = "") -> str:
    label = f"{emoji} {title}" if emoji else title
    return f"{bold(label)}\n{DIVIDER}"


def subsection(title: str) -> str:
    return bold(f"▸ {title}")


def row(emoji: str, label: str, value: str) -> str:
    return f"{emoji} {dim(label)}  {value}"


def symbol_card(symbol: str) -> str:
    return f"◆ {bold(symbol)}"


def empty(msg: str = "데이터 없음") -> str:
    return f"📭 {dim(msg)}"


def t_transition(t_before: object, t_after: object) -> str:
    """T 변화 표기 — 'T 12→13' / 'T 13' / 'T —'. 매매 기록 전반에서 공통 사용."""
    def _num(val: object) -> float | None:
        if val in (None, ""):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    before, after = _num(t_before), _num(t_after)
    if before is not None and after is not None and before != after:
        return f"T {before:g}→{after:g}"
    if after is not None:
        return f"T {after:g}"
    if before is not None:
        return f"T {before:g}"
    return "T —"


def signed_usd_text(amount: float, decimals: int = 2) -> str:
    """부호 포함 금액 — escape 대상이 아닌 순수 숫자 텍스트."""
    sign = "+" if amount >= 0 else ""
    return esc(f"{sign}${amount:,.{decimals}f}")
