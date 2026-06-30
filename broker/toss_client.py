"""Toss Open API HTTP client."""

import logging
import uuid

import requests

from broker.toss_auth import BASE_URL, TossAuth
from broker.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _money(val, currency: str = "usd") -> float:
    """Parse Toss Price / amount fields (decimal strings or {krw, usd})."""
    if val is None:
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
            for key in ("total", "us", "kr"):
                nested = val.get(key)
                if isinstance(nested, dict):
                    return _money(nested, currency)
        if raw in (None, ""):
            return 0.0
        return float(raw)
    return 0.0


def _pct(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, dict):
        for key in ("rate", "rateAfterCost", "profitRate"):
            if key in val and val[key] not in (None, ""):
                return float(val[key]) * 100
        return None
    try:
        return float(val) * 100
    except (TypeError, ValueError):
        return None


class TossClient:
    def __init__(self, auth: TossAuth, account_seq: str, limiter: RateLimiter, dry_run: bool = False):
        self.auth = auth
        self.account_seq = account_seq
        self.limiter = limiter
        self.dry_run = dry_run

    def _headers(self, with_account: bool = False) -> dict:
        h = {"Authorization": f"Bearer {self.auth.get_token()}"}
        if with_account:
            h["X-Tossinvest-Account"] = str(self.account_seq)
        return h

    def _request(self, method: str, path: str, group: str, account: bool = False, **kwargs):
        self.limiter.acquire(group)
        url = f"{BASE_URL}{path}"
        headers = self._headers(with_account=account)
        headers.update(kwargs.pop("headers", {}))
        res = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        if res.status_code == 401:
            self.auth.invalidate()
            headers = self._headers(with_account=account)
            res = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        if res.status_code == 429:
            retry = int(res.headers.get("Retry-After", "2"))
            logger.warning("Rate limited, wait %ss", retry)
            import time
            time.sleep(retry)
            return self._request(method, path, group, account, **kwargs)
        res.raise_for_status()
        return res.json()

    def get_price(self, symbol: str) -> float:
        if self.dry_run:
            return 0.0
        data = self._request("GET", "/api/v1/prices", "MARKET_DATA", params={"symbol": symbol.upper()})
        result = data.get("result", data)
        return float(result.get("lastPrice", 0))

    def get_holdings_overview(self) -> dict | None:
        if self.dry_run:
            return None
        data = self._request("GET", "/api/v1/holdings", "ASSET", account=True)
        return data.get("result", data)

    def get_buying_power(self, currency: str = "USD") -> dict:
        if self.dry_run:
            return {}
        data = self._request(
            "GET",
            "/api/v1/buying-power",
            "ORDER_INFO",
            account=True,
            params={"currency": currency.upper()},
        )
        return data.get("result", data)

    def get_holdings_item(self, symbol: str) -> dict:
        if self.dry_run:
            return {"qty": 0, "avg_price": 0.0, "current_price": 0.0}
        overview = self.get_holdings_overview() or {}
        items = overview.get("items", [])
        qty, avg, mkt = 0, 0.0, 0.0
        for item in items:
            if item.get("symbol", "").upper() == symbol.upper():
                qty = int(float(item.get("quantity", 0)))
                cost = item.get("cost", {})
                avg = float(cost.get("averagePrice", 0) or item.get("averagePurchasePrice", 0) or 0)
                mkt = _money(item.get("marketValue"), "usd")
                if mkt == 0:
                    mkt = float(item.get("lastPrice", 0) or 0) * qty
                break
        price = self.get_price(symbol) if mkt == 0 and qty > 0 else (mkt / qty if qty else 0)
        return {"qty": qty, "avg_price": avg, "current_price": price}

    def place_limit_order(self, symbol: str, side: str, price: float, qty: int) -> bool:
        if self.dry_run:
            logger.info("[DRY_RUN] LOC대체 LIMIT %s %s %s @ %s", side, qty, symbol, price)
            return True
        # Toss: LOC 없음 → 장마감 직전 LIMIT+DAY (종가>=매도가 / 종가<=매수가 에 체결)
        body = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "orderType": "LIMIT",
            "timeInForce": "DAY",
            "quantity": qty,
            "price": str(round(price, 2)),
            "clientOrderId": str(uuid.uuid4()),
        }
        self._request("POST", "/api/v1/orders", "ORDER", account=True, json=body)
        return True

    def is_us_market_open_today(self) -> bool:
        if self.dry_run:
            return True
        try:
            data = self._request("GET", "/api/v1/market-calendar/US", "MARKET_INFO")
            result = data.get("result", data)
            today = result.get("today", {})
            return today.get("regularMarket") is not None
        except Exception:
            return True
