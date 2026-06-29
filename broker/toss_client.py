"""Toss Open API HTTP client."""

import logging
import uuid

import requests

from broker.toss_auth import BASE_URL, TossAuth
from broker.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


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
        data = self._request("GET", "/prices", "MARKET_DATA", params={"symbol": symbol.upper()})
        result = data.get("result", data)
        return float(result.get("lastPrice", 0))

    def get_holdings_item(self, symbol: str) -> dict:
        if self.dry_run:
            return {"qty": 0, "avg_price": 0.0, "current_price": 0.0, "api_cash_usd": 0.0}
        data = self._request("GET", "/holdings", "ASSET", account=True)
        result = data.get("result", data)
        items = result.get("items", [])
        qty, avg, mkt = 0, 0.0, 0.0
        for item in items:
            if item.get("symbol", "").upper() == symbol.upper():
                qty = int(float(item.get("quantity", 0)))
                cost = item.get("cost", {})
                avg = float(cost.get("averagePrice", 0) or 0)
                mkt = float(item.get("marketValue", 0) or 0)
                break
        api_cash = 0.0
        overview = result.get("marketValue", {})
        if isinstance(overview, dict) and overview.get("usd"):
            pass
        price = self.get_price(symbol) if mkt == 0 and qty > 0 else (mkt / qty if qty else 0)
        return {"qty": qty, "avg_price": avg, "current_price": price, "api_cash_usd": api_cash}

    def place_limit_order(self, symbol: str, side: str, price: float, qty: int) -> bool:
        if self.dry_run:
            logger.info("[DRY_RUN] %s %s %s @ %s", side, qty, symbol, price)
            return True
        body = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "orderType": "LIMIT",
            "timeInForce": "DAY",
            "quantity": qty,
            "price": str(round(price, 2)),
            "clientOrderId": str(uuid.uuid4()),
        }
        self._request("POST", "/orders", "ORDER", account=True, json=body)
        return True

    def is_us_market_open_today(self) -> bool:
        if self.dry_run:
            return True
        try:
            data = self._request("GET", "/market-calendar/US", "MARKET_INFO")
            result = data.get("result", data)
            today = result.get("today", {})
            return today.get("regularMarket") is not None
        except Exception:
            return True
