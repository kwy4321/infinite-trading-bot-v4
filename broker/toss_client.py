"""Toss Open API HTTP client."""

import datetime
import logging
import time
import uuid
from zoneinfo import ZoneInfo

import requests

from broker.toss_auth import BASE_URL, TossAuth
from broker.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")


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
        self._holdings_cache: dict | None = None
        self._holdings_cache_at: float = 0.0

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
        now = time.monotonic()
        if self._holdings_cache is not None and now - self._holdings_cache_at < 10:
            return self._holdings_cache
        data = self._request("GET", "/api/v1/holdings", "ASSET", account=True)
        result = data.get("result", data)
        self._holdings_cache = result
        self._holdings_cache_at = now
        return result

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

    def get_exchange_rate(self, base: str = "USD", quote: str = "KRW") -> dict:
        if self.dry_run:
            return {}
        data = self._request(
            "GET",
            "/api/v1/exchange-rate",
            "MARKET_INFO",
            params={"baseCurrency": base.upper(), "quoteCurrency": quote.upper()},
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

    def _parse_order_response(self, data: dict) -> dict:
        result = data.get("result", data)
        return {
            "order_id": str(result.get("orderId") or result.get("order_id") or ""),
            "client_order_id": result.get("clientOrderId") or result.get("client_order_id"),
        }

    def _parse_order_detail(self, data: dict) -> dict:
        result = data.get("result", data)
        exec_ = result.get("execution") or {}
        qty_raw = result.get("quantity") or 0
        filled_raw = (
            exec_.get("filledQuantity") or exec_.get("filled_quantity") or 0
        )
        avg_raw = exec_.get("averageFilledPrice") or exec_.get("average_filled_price")
        return {
            "order_id": str(result.get("orderId") or result.get("order_id") or ""),
            "status": str(result.get("status") or ""),
            "symbol": str(result.get("symbol") or ""),
            "side": str(result.get("side") or ""),
            "quantity": float(qty_raw or 0),
            "filled_quantity": float(filled_raw or 0),
            "average_filled_price": float(avg_raw) if avg_raw not in (None, "") else None,
        }

    def get_order(self, order_id: str) -> dict:
        if self.dry_run or not order_id:
            return {}
        data = self._request(
            "GET", f"/api/v1/orders/{order_id}", "ORDER_HISTORY", account=True,
        )
        return self._parse_order_detail(data)

    def wait_for_fill(
        self, order_id: str, timeout_sec: float = 20.0, poll_sec: float = 0.5,
    ) -> dict:
        """주문 체결 대기 — 타임아웃 시 마지막 상태 반환."""
        if self.dry_run or not order_id:
            return {}
        deadline = time.monotonic() + timeout_sec
        last: dict = {}
        terminal_reject = {"REJECTED", "CANCELED", "CANCELLED", "REPLACE_REJECTED"}
        while time.monotonic() < deadline:
            last = self.get_order(order_id)
            status = (last.get("status") or "").upper().replace("-", "_")
            filled = float(last.get("filled_quantity") or 0)
            qty = float(last.get("quantity") or 0)
            if filled > 0 and (status == "FILLED" or (qty > 0 and filled >= qty)):
                return last
            if status in terminal_reject:
                return last
            if filled > 0 and status in ("PARTIAL_FILLED", "PARTIALFILLED"):
                return last
            time.sleep(poll_sec)
        return last or self.get_order(order_id)

    def _invalidate_holdings_cache(self) -> None:
        self._holdings_cache = None
        self._holdings_cache_at = 0.0

    def place_limit_order(self, symbol: str, side: str, price: float, qty: int) -> dict:
        client_order_id = str(uuid.uuid4())
        if self.dry_run:
            logger.info("[DRY_RUN] LOC대체 LIMIT %s %s %s @ %s", side, qty, symbol, price)
            return {"order_id": f"dry-{client_order_id[:8]}", "client_order_id": client_order_id}
        body = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "orderType": "LIMIT",
            "timeInForce": "DAY",
            "quantity": qty,
            "price": str(round(price, 2)),
            "clientOrderId": client_order_id,
        }
        data = self._request("POST", "/api/v1/orders", "ORDER", account=True, json=body)
        self._invalidate_holdings_cache()
        return self._parse_order_response(data)

    def place_market_order(self, symbol: str, side: str, qty: int) -> dict:
        """시장가 주문 — 장 마감 LOC 흉내. order_id 반환."""
        client_order_id = str(uuid.uuid4())
        if self.dry_run:
            logger.info("[DRY_RUN] MARKET %s %s %s", side, qty, symbol)
            return {"order_id": f"dry-{client_order_id[:8]}", "client_order_id": client_order_id}
        body = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "orderType": "MARKET",
            "timeInForce": "DAY",
            "quantity": qty,
            "clientOrderId": client_order_id,
        }
        data = self._request("POST", "/api/v1/orders", "ORDER", account=True, json=body)
        self._invalidate_holdings_cache()
        return self._parse_order_response(data)

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        if self.dry_run:
            return []
        data = self._request(
            "GET", "/api/v1/orders", "ORDER_HISTORY", account=True, params={"status": "OPEN"},
        )
        result = data.get("result", data)
        orders = list(result.get("orders") or [])
        if symbol:
            sym = symbol.upper()
            orders = [o for o in orders if (o.get("symbol") or "").upper() == sym]
        return orders

    def _parse_session_time(self, raw: str) -> datetime.time:
        parts = raw.split(":")
        return datetime.time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

    def _in_session(self, now_kst: datetime.datetime, session: dict | None) -> bool:
        if not session:
            return False
        start = self._parse_session_time(session["startTime"])
        end = self._parse_session_time(session["endTime"])
        now_t = now_kst.time()
        if start <= end:
            return start <= now_t <= end
        return now_t >= start or now_t <= end

    def _market_status_from_calendar(self, day: dict) -> str:
        if not day.get("regularMarket"):
            return "closed"
        now_kst = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
        checks = (
            ("day", day.get("dayMarket")),
            ("premarket", day.get("preMarket")),
            ("regular", day.get("regularMarket")),
            ("afterhours", day.get("afterMarket")),
        )
        for status, session in checks:
            if self._in_session(now_kst, session):
                return status
        return "off_hours"

    def _market_status_fallback(self) -> str:
        now_ny = datetime.datetime.now(ZoneInfo("America/New_York"))
        if now_ny.weekday() >= 5:
            return "closed"
        t = now_ny.time()
        if datetime.time(9, 30) <= t < datetime.time(16, 0):
            return "regular"
        if datetime.time(4, 0) <= t < datetime.time(9, 30):
            return "premarket"
        if datetime.time(16, 0) <= t < datetime.time(20, 0):
            return "afterhours"
        return "off_hours"

    def get_us_market_calendar(self) -> dict:
        if self.dry_run:
            today = datetime.datetime.now(NY).date().isoformat()
            return {
                "today": {"date": today, "regularMarket": {"startTime": "00:00", "endTime": "00:00"}},
                "nextBusinessDay": {"date": today, "regularMarket": {"startTime": "00:00", "endTime": "00:00"}},
                "previousBusinessDay": {"date": today, "regularMarket": {"startTime": "00:00", "endTime": "00:00"}},
            }
        data = self._request("GET", "/api/v1/market-calendar/US", "MARKET_INFO")
        return data.get("result", data)

    @staticmethod
    def find_us_market_day(cal: dict, target_date: str) -> dict | None:
        for key in ("today", "nextBusinessDay", "previousBusinessDay"):
            day = cal.get(key) or {}
            if day.get("date") == target_date:
                return day
        return None

    def check_us_regular_session(self, target_date: str) -> tuple[bool, str]:
        """Return (has_regular_session, us_date) for the given US calendar date."""
        if self.dry_run:
            return True, target_date
        try:
            cal = self.get_us_market_calendar()
            day = self.find_us_market_day(cal, target_date)
            if not day:
                day = cal.get("today") or {}
            us_date = day.get("date", target_date)
            return day.get("regularMarket") is not None, us_date
        except Exception:
            logger.exception("US market calendar check failed")
            return True, target_date

    @staticmethod
    def target_us_date_for_morning_job(kst_now: datetime.datetime | None = None) -> str:
        """KST 새벽 Job — 오늘 밤(한국) 열릴 미국 정규장 = KST 날짜와 같은 US 거래일."""
        now = kst_now or datetime.datetime.now(KST)
        return now.date().isoformat()

    @staticmethod
    def target_us_date_for_ny_job(kst_now: datetime.datetime | None = None) -> str:
        """미국 동부 시각 기준 당일 거래일."""
        now = kst_now or datetime.datetime.now(KST)
        return now.astimezone(NY).date().isoformat()

    def get_us_market_status(self) -> str:
        """Return US market phase: regular, premarket, afterhours, day, off_hours, closed."""
        if self.dry_run:
            return self._market_status_fallback()
        try:
            data = self._request("GET", "/api/v1/market-calendar/US", "MARKET_INFO")
            result = data.get("result", data)
            return self._market_status_from_calendar(result.get("today", {}))
        except Exception:
            return self._market_status_fallback()

    def is_us_market_open_today(self) -> bool:
        """대시보드용 — 지금 시각 기준 다음/당일 미국 정규장 개장 여부."""
        now = datetime.datetime.now(KST)
        if now.hour < 12:
            target = self.target_us_date_for_morning_job(now)
        else:
            target = self.target_us_date_for_ny_job(now)
        open_, _ = self.check_us_regular_session(target)
        return open_
