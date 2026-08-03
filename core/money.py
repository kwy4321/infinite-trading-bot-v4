"""토스 Open API 금액 파싱 단일 소스.

Toss 는 금액을 숫자, 소수 문자열, {"krw": ..., "usd": ...} 중 아무 형태로 준다.
파싱 규칙이 여러 모듈에 흩어지면 통화 단위 버그가 생기므로 여기만 사용한다.
"""

from __future__ import annotations

_NESTED_KEYS = ("total", "us", "kr")
_PCT_KEYS = ("rate", "rateAfterCost", "profitRate")


def parse_money(val: object, currency: str = "usd") -> float:
    """숫자 / 문자열 / {krw, usd} → float. 파싱 실패는 0.0."""
    if val is None:
        return 0.0
    if isinstance(val, bool):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    if isinstance(val, dict):
        cur = currency.lower()
        raw = val.get(cur)
        if raw in (None, "") and cur == "usd":
            raw = val.get("us")
        if raw in (None, ""):
            raw = val.get("krw") or val.get("kr")
        if raw in (None, ""):
            for key in _NESTED_KEYS:
                nested = val.get(key)
                if isinstance(nested, dict):
                    return parse_money(nested, currency)
        if raw in (None, ""):
            return 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def parse_pct(val: object) -> float | None:
    """수익률 필드 → 퍼센트 값. 토스는 비율(0.05)로 주므로 ×100 한다. 없으면 None."""
    if val is None:
        return None
    if isinstance(val, dict):
        for key in _PCT_KEYS:
            raw = val.get(key)
            if raw not in (None, ""):
                try:
                    return float(raw) * 100
                except (TypeError, ValueError):
                    return None
        return None
    try:
        return float(val) * 100
    except (TypeError, ValueError):
        return None


def _buying_power_raw(buying: dict | None) -> object:
    if not buying:
        return None
    return buying.get("cashBuyingPower", buying.get("cash", buying))


def cash_usd(buying: dict | None) -> float:
    """buyingPower 응답 → USD 현금."""
    raw = _buying_power_raw(buying)
    if raw is None:
        return 0.0
    if isinstance(raw, dict):
        return parse_money(raw, "usd")
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def cash_krw(buying: dict | None) -> float:
    """buyingPower 응답 → KRW 현금."""
    raw = _buying_power_raw(buying)
    if raw is None:
        return 0.0
    return parse_money(raw, "krw")


def holding_avg_price(item: dict) -> float:
    """보유 종목 항목 → 평단. averagePurchasePrice 없으면 cost.averagePrice."""
    avg = parse_money(item.get("averagePurchasePrice"), "usd")
    if avg > 0:
        return avg
    cost = item.get("cost")
    if isinstance(cost, dict):
        return parse_money(cost.get("averagePrice"), "usd")
    return 0.0


def holding_market_value(item: dict, currency: str = "usd") -> float:
    """보유 종목 항목 → 평가금액. marketValue 없으면 수량 × 현재가."""
    mkt = parse_money(item.get("marketValue"), currency)
    if mkt > 0:
        return mkt
    if currency.lower() != "usd":
        return 0.0
    qty = parse_money(item.get("quantity"), "usd")
    last = parse_money(item.get("lastPrice"), "usd")
    return round(qty * last, 4) if qty and last else 0.0


def holding_unrealized(item: dict) -> tuple[float, float | None]:
    """보유 종목 항목 → (미실현 USD, 미실현 %). 응답 필드 없으면 평단으로 계산."""
    for key in ("evaluationProfitLoss", "profitLoss", "profit", "unrealizedProfitLoss"):
        val = item.get(key)
        if val is None:
            continue
        amount = parse_money(val, "usd")
        pct = parse_pct(val)
        if amount != 0 or pct is not None:
            return amount, pct
    qty = parse_money(item.get("quantity"), "usd")
    avg = holding_avg_price(item)
    last = parse_money(item.get("lastPrice"), "usd")
    if qty > 0 and avg > 0 and last > 0:
        return round((last - avg) * qty, 2), round((last - avg) / avg * 100, 2)
    return 0.0, None
