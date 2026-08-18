"""매도 체결 실현손익 — 브리핑·매매내역 공통 계산."""

from __future__ import annotations


def sell_avg_cost(tr: dict) -> float | None:
    """매도 직전 평단 — avg_before 우선, 일부 매도는 avg_after."""
    avg_before = tr.get("avg_before")
    if avg_before not in (None, ""):
        cost = float(avg_before)
        return cost if cost > 0 else None

    qty_after = int(tr.get("qty_after") or 0)
    avg_after = float(tr.get("avg_after") or 0)
    if qty_after > 0 and avg_after > 0:
        return avg_after
    return None


def sell_realized_pnl(tr: dict) -> tuple[float, float] | None:
    """매도 1건 (USD, %) — profit_usd 저장값 우선."""
    if str(tr.get("side") or "").upper() != "SELL":
        return None

    if tr.get("profit_usd") is not None:
        pnl = float(tr["profit_usd"])
        pct = float(tr.get("profit_pct") or 0)
        return pnl, pct

    qty = int(tr.get("qty") or 0)
    price = float(tr.get("price") or 0)
    if qty <= 0 or price <= 0:
        return None

    avg_cost = sell_avg_cost(tr)
    if avg_cost is None or avg_cost <= 0:
        return None

    pnl = round((price - avg_cost) * qty, 2)
    pct = round((price - avg_cost) / avg_cost * 100, 2)
    return pnl, pct


def sell_profit_fields(
    *, price: float, qty: int, avg_before: float,
) -> dict[str, float]:
    """record_trade / fill_log 저장용."""
    if avg_before <= 0 or qty <= 0:
        return {}
    pnl = round((price - avg_before) * qty, 2)
    pct = round((price - avg_before) / avg_before * 100, 2)
    return {"profit_usd": pnl, "profit_pct": pct}


def principal_after_graduation(completed: dict) -> float:
    """회차 졸업 시 다음 회차 복리 원금."""
    return max(0.0, round(
        float(completed.get("principal", 0)) + float(completed.get("profit_usd", 0)), 2,
    ))
