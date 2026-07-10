"""Toss Open API HTTP client."""

from __future__ import annotations

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
_FILLS_CACHE_MAX = 32


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
        self._calendar_cache: dict | None = None
        self._calendar_cache_at: float = 0.0
        self._fills_cache: dict[str, tuple[float, list]] = {}

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
        if not res.ok:
            try:
                err = res.json()
            except ValueError:
                err = res.text
            logger.error("Toss API %s %s failed (%s): %s", method, path, res.status_code, err)
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
        ordered_at = result.get("orderedAt") or result.get("ordered_at") or ""
        exec_filled = exec_.get("filledAt") or exec_.get("filled_at") or ""
        return {
            "order_id": str(result.get("orderId") or result.get("order_id") or ""),
            "status": str(result.get("status") or ""),
            "symbol": str(result.get("symbol") or ""),
            "side": str(result.get("side") or ""),
            "quantity": float(qty_raw or 0),
            "filled_quantity": float(filled_raw or 0),
            "average_filled_price": float(avg_raw) if avg_raw not in (None, "") else None,
            "ordered_at": str(ordered_at) if ordered_at else "",
            "filled_at": str(exec_filled or ordered_at or ""),
            "execution": exec_,
        }

    def get_order(self, order_id: str) -> dict:
        if self.dry_run or not order_id:
            return {}
        data = self._request(
            "GET", f"/api/v1/orders/{order_id}", "ORDER_HISTORY", account=True,
        )
        return self._parse_order_detail(data)

    def wait_for_fill(
        self, order_id: str, timeout_sec: float = 90.0, poll_sec: float = 1.0,
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
        self._fills_cache.clear()

    def _get_us_market_calendar_cached(self) -> dict:
        now = time.monotonic()
        if self._calendar_cache is not None and now - self._calendar_cache_at < 3600:
            return self._calendar_cache
        if self.dry_run:
            today = datetime.datetime.now(NY).date().isoformat()
            cal = {
                "today": {"date": today, "regularMarket": {"startTime": "00:00", "endTime": "00:00"}},
                "nextBusinessDay": {"date": today, "regularMarket": {"startTime": "00:00", "endTime": "00:00"}},
                "previousBusinessDay": {"date": today, "regularMarket": {"startTime": "00:00", "endTime": "00:00"}},
            }
        else:
            data = self._request("GET", "/api/v1/market-calendar/US", "MARKET_INFO")
            cal = data.get("result", data)
        self._calendar_cache = cal
        self._calendar_cache_at = now
        return cal

    def place_limit_order(self, symbol: str, side: str, price: float, qty: int) -> dict:
        client_order_id = str(uuid.uuid4())
        if self.dry_run:
            logger.info("[DRY_RUN] LIMIT DAY %s %s %s @ %s", side, qty, symbol, price)
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

    def place_loc_order(self, symbol: str, side: str, price: float, qty: int) -> dict:
        """LOC — 미국 종가 지정가 (orderType=LIMIT, timeInForce=CLS)."""
        client_order_id = str(uuid.uuid4())
        if self.dry_run:
            logger.info("[DRY_RUN] LOC %s %s %s @ %s", side, qty, symbol, price)
            return {"order_id": f"dry-{client_order_id[:8]}", "client_order_id": client_order_id}
        body = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "orderType": "LIMIT",
            "timeInForce": "CLS",
            "quantity": qty,
            "price": str(round(price, 2)),
            "clientOrderId": client_order_id,
        }
        data = self._request("POST", "/api/v1/orders", "ORDER", account=True, json=body)
        self._invalidate_holdings_cache()
        return self._parse_order_response(data)

    def place_market_order(self, symbol: str, side: str, qty: int) -> dict:
        """시장가 주문. order_id 반환."""
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

    def get_closed_orders(
        self,
        symbol: str | None = None,
        *,
        limit: int = 100,
        max_orders: int = 200,
        from_date: str | None = None,
    ) -> list[dict]:
        """종료된 주문 목록 — execution.filledAt 포함 (페이지네이션)."""
        if self.dry_run:
            return []
        page_size = min(max(limit, 1), 100)
        cap = max(max_orders, page_size)
        params: dict = {"status": "CLOSED", "limit": page_size}
        if symbol:
            params["symbol"] = symbol.upper()
        if from_date:
            params["from"] = from_date
        all_orders: list[dict] = []
        cursor: str | None = None
        while len(all_orders) < cap:
            req = dict(params)
            if cursor:
                req["cursor"] = cursor
            data = self._request(
                "GET", "/api/v1/orders", "ORDER_HISTORY", account=True, params=req,
            )
            result = data.get("result", data)
            batch = list(result.get("orders") or [])
            all_orders.extend(batch)
            if not result.get("hasNext") or not result.get("nextCursor"):
                break
            cursor = str(result.get("nextCursor"))
        return all_orders[:cap]

    @staticmethod
    def _execution_avg_price(order: dict) -> float | None:
        """체결 평균가 — order.price(지정가)는 사용하지 않음."""
        exec_ = order.get("execution") or {}
        avg = (
            exec_.get("averageFilledPrice") or exec_.get("average_filled_price")
            or order.get("average_filled_price") or order.get("averageFilledPrice")
        )
        if avg in (None, ""):
            return None
        return round(float(avg), 4)

    def _order_to_fill(self, order: dict, symbol: str | None = None) -> dict | None:
        sym = str(order.get("symbol") or "").upper()
        if symbol and sym and sym != symbol.upper():
            return None
        exec_ = order.get("execution") or {}
        qty = int(float(
            exec_.get("filledQuantity") or exec_.get("filled_quantity")
            or order.get("filled_quantity") or order.get("filledQuantity") or 0
        ))
        status = str(order.get("status") or "").upper()
        if qty <= 0 and status == "FILLED":
            qty = int(float(order.get("quantity") or order.get("qty") or 0))
        if qty <= 0:
            return None
        avg = self._execution_avg_price(order)
        if avg is None:
            return None
        ordered_at = self.order_placed_timestamp(order)
        filled_at = self.order_fill_timestamp(order) or ordered_at
        oid = str(order.get("orderId") or order.get("order_id") or "")
        if not oid or not (ordered_at or filled_at):
            return None
        return {
            "order_id": oid,
            "symbol": sym,
            "side": str(order.get("side") or "").upper(),
            "qty": qty,
            "price": round(float(avg), 2),
            "ordered_at": ordered_at or filled_at,
            "filled_at": filled_at or ordered_at,
        }

    @staticmethod
    def _fill_record_complete(fill: dict) -> bool:
        return bool(
            fill.get("order_id")
            and float(fill.get("price") or 0) > 0
            and (fill.get("ordered_at") or fill.get("filled_at"))
        )

    def _enrich_fill_from_order(self, fill: dict, symbol: str | None = None) -> dict | None:
        """단건 조회로 averageFilledPrice 확정 — CLOSED에 체결가가 없을 때만."""
        if self._fill_record_complete(fill):
            return fill
        oid = str(fill.get("order_id") or "")
        if not oid:
            return fill
        try:
            detail = self.get_order(oid)
            refined = self._detail_to_fill(detail, symbol)
            if refined:
                return refined
        except Exception:
            logger.exception("enrich fill from get_order failed %s", oid)
        return fill

    @staticmethod
    def _collect_order_id(order: dict) -> str:
        return str(order.get("orderId") or order.get("order_id") or "").strip()

    def _detail_to_fill(self, detail: dict, symbol: str | None = None) -> dict | None:
        if not detail:
            return None
        sym = str(detail.get("symbol") or "").upper()
        if symbol and sym and sym != symbol.upper():
            return None
        qty = int(float(detail.get("filled_quantity") or 0))
        if qty <= 0:
            return None
        ordered_at = str(detail.get("ordered_at") or "")
        filled_at = str(detail.get("filled_at") or ordered_at or "")
        oid = str(detail.get("order_id") or "")
        if not oid or not (ordered_at or filled_at):
            return None
        avg = detail.get("average_filled_price")
        if avg in (None, ""):
            return None
        return {
            "order_id": oid,
            "symbol": sym,
            "side": str(detail.get("side") or "").upper(),
            "qty": qty,
            "price": round(float(avg), 2),
            "ordered_at": ordered_at or filled_at,
            "filled_at": filled_at or ordered_at,
        }

    def list_broker_fills(
        self,
        symbol: str,
        *,
        days: int = 90,
        max_orders: int = 200,
        extra_order_ids: list[str] | None = None,
    ) -> list[dict]:
        """체결 주문 — CLOSED 목록 + 알려진 orderId 단건 조회 fallback."""
        sym = symbol.upper()
        id_key = ",".join(sorted(str(x) for x in (extra_order_ids or []) if x))
        cache_key = f"{sym}:{id_key}"
        now = time.monotonic()
        cached = self._fills_cache.get(cache_key)
        if cached and now - cached[0] < 60:
            return list(cached[1])

        from_date = (
            datetime.datetime.now(KST) - datetime.timedelta(days=days)
        ).date().isoformat()
        fills: list[dict] = []
        seen: set[str] = set()
        pending_oids: list[str] = []

        def add_fill(raw: dict | None) -> None:
            if not raw:
                return
            oid = str(raw.get("order_id") or "")
            if not oid or oid in seen:
                return
            seen.add(oid)
            fills.append(raw)

        closed_attempts = [
            {"symbol": symbol, "from_date": from_date},
            {"symbol": symbol, "from_date": None},
        ]
        for params in closed_attempts:
            try:
                orders = self.get_closed_orders(
                    params["symbol"],
                    from_date=params["from_date"],
                    max_orders=max_orders,
                )
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code == 400:
                    logger.warning("CLOSED order list rejected (%s): %s", params, exc)
                    continue
                raise
            for order in orders:
                parsed = self._order_to_fill(order, symbol)
                if parsed:
                    add_fill(parsed)
                else:
                    oid = self._collect_order_id(order)
                    if oid and oid not in seen and oid not in pending_oids:
                        pending_oids.append(oid)

        if not fills:
            for params in (
                {"symbol": None, "from_date": from_date},
                {"symbol": None, "from_date": None},
            ):
                try:
                    orders = self.get_closed_orders(
                        params["symbol"],
                        from_date=params["from_date"],
                        max_orders=max_orders,
                    )
                except requests.HTTPError as exc:
                    code = exc.response.status_code if exc.response is not None else None
                    if code == 400:
                        logger.warning("CLOSED order list rejected (%s): %s", params, exc)
                        continue
                    raise
                for order in orders:
                    parsed = self._order_to_fill(order, symbol)
                    if parsed:
                        add_fill(parsed)
                    else:
                        oid = self._collect_order_id(order)
                        if oid and oid not in seen and oid not in pending_oids:
                            pending_oids.append(oid)
                if fills:
                    break

        for oid in list(pending_oids) + list(extra_order_ids or []):
            oid = str(oid or "").strip()
            if not oid or oid in seen:
                continue
            try:
                detail = self.get_order(oid)
                add_fill(self._detail_to_fill(detail, symbol))
            except Exception:
                logger.exception("get_order fill fetch failed %s", oid)

        enriched: list[dict] = []
        for raw in fills:
            item = self._enrich_fill_from_order(raw, sym)
            if item:
                enriched.append(item)
        fills = enriched
        fills.sort(key=lambda f: f["ordered_at"])
        self._store_fills_cache(cache_key, now, fills)
        return fills

    def _store_fills_cache(self, key: str, at: float, fills: list[dict]) -> None:
        if len(self._fills_cache) >= _FILLS_CACHE_MAX:
            oldest = min(self._fills_cache, key=lambda k: self._fills_cache[k][0])
            del self._fills_cache[oldest]
        self._fills_cache[key] = (at, list(fills))

    @staticmethod
    def order_placed_timestamp(order: dict) -> str:
        """주문 접수 시각 orderedAt (토스 주문내역 날짜 기준)."""
        for val in (
            order.get("orderedAt"), order.get("ordered_at"),
        ):
            if val:
                return str(val)
        return ""

    @staticmethod
    def order_fill_timestamp(order: dict) -> str:
        """체결 시각 filledAt (결제/체결 기준)."""
        exec_ = order.get("execution") or {}
        for val in (
            exec_.get("filledAt"), exec_.get("filled_at"),
            order.get("filledAt"), order.get("filled_at"),
        ):
            if val:
                return str(val)
        return ""

    @staticmethod
    def build_order_fill_times(orders: list[dict]) -> dict[str, str]:
        """orderId → filledAt 매핑."""
        out: dict[str, str] = {}
        for order in orders:
            oid = str(order.get("orderId") or order.get("order_id") or "")
            ts = TossClient.order_fill_timestamp(order)
            if oid and ts:
                out[oid] = ts
        return out

    def _parse_session_time(self, raw: str) -> datetime.time:
        """HH:MM 또는 HH:MM:SS (레거시)."""
        text = str(raw).strip()
        if "T" in text:
            dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt.astimezone(KST).time()
        parts = text.split(":")
        sec = parts[2] if len(parts) > 2 else "0"
        sec = sec.split("+")[0].split("-")[0]
        return datetime.time(int(parts[0]), int(parts[1]), int(sec))

    def _parse_session_instant(self, raw: str | None) -> datetime.datetime | None:
        """토스 캘린더 startTime/endTime — ISO(+09:00) 또는 HH:MM:SS."""
        if not raw:
            return None
        text = str(raw).strip()
        try:
            if "T" in text:
                dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
                return dt.astimezone(KST)
            t = self._parse_session_time(text)
            today = datetime.datetime.now(KST).date()
            return datetime.datetime.combine(today, t, tzinfo=KST)
        except (ValueError, TypeError):
            logger.warning("invalid session time %r", raw)
            return None

    def _in_session(self, now_kst: datetime.datetime, session: dict | None) -> bool:
        if not session:
            return False
        start_raw = session.get("startTime") or session.get("start_time") or ""
        end_raw = session.get("endTime") or session.get("end_time") or ""
        if "T" in str(start_raw) or "T" in str(end_raw):
            start = self._parse_session_instant(start_raw)
            end = self._parse_session_instant(end_raw)
            if start and end:
                return start <= now_kst <= end
            return False
        try:
            start = self._parse_session_time(str(start_raw))
            end = self._parse_session_time(str(end_raw))
        except (ValueError, TypeError):
            return False
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
        return self._get_us_market_calendar_cached()

    @staticmethod
    def find_us_market_day(cal: dict, target_date: str) -> dict | None:
        for key in ("today", "nextBusinessDay", "previousBusinessDay"):
            day = cal.get(key) or {}
            if day.get("date") == target_date:
                return day
        return None

    def check_us_regular_session(self, target_date: str) -> tuple[bool, str, bool]:
        """Return (has_regular_session, us_date, calendar_ok). API 실패 시 fail-closed."""
        if self.dry_run:
            return True, target_date, True
        try:
            cal = self.get_us_market_calendar()
            day = self.find_us_market_day(cal, target_date)
            if not day:
                day = cal.get("today") or {}
            us_date = day.get("date", target_date)
            return day.get("regularMarket") is not None, us_date, True
        except Exception:
            logger.exception("US market calendar check failed")
            return False, target_date, False

    def is_us_loc_session_now(self) -> bool:
        """프리마켓·정규장 — LOC(CLS) 접수 가능 구간."""
        if self.dry_run:
            return True
        try:
            cal = self._get_us_market_calendar_cached()
            day = cal.get("today") or {}
            if not day.get("regularMarket"):
                return False
            now_kst = datetime.datetime.now(KST)
            for session in (day.get("preMarket"), day.get("regularMarket")):
                if session and self._in_session(now_kst, session):
                    return True
        except Exception:
            logger.exception("is_us_loc_session_now calendar check failed")
        return self._market_status_fallback() in ("premarket", "regular")

    def is_us_regular_session_now(self) -> bool:
        """미국 정규장 시간."""
        if self.dry_run:
            return True
        cal = self._get_us_market_calendar_cached()
        day = cal.get("today") or {}
        if not day.get("regularMarket"):
            return False
        return self._in_session(datetime.datetime.now(KST), day.get("regularMarket"))

    def is_us_market_open_today(self) -> bool:
        """대시보드용 — 지금 시각 기준 다음/당일 미국 정규장 개장 여부."""
        now = datetime.datetime.now(KST)
        if now.hour < 12:
            target = self.target_us_date_for_morning_job(now)
        else:
            target = self.target_us_date_for_ny_job(now)
        open_, _, cal_ok = self.check_us_regular_session(target)
        return open_ if cal_ok else False

    @staticmethod
    def target_us_date_for_morning_job(kst_now: datetime.datetime | None = None) -> str:
        """KST 새벽 Job — 오늘 밤(한국) 열릴 미국 정규장 = KST 날짜와 같은 US 거래일."""
        now = kst_now or datetime.datetime.now(KST)
        return now.date().isoformat()

    @staticmethod
    def target_us_date_for_evening_loc(kst_now: datetime.datetime | None = None) -> str:
        """저녁(18:05 KST) 프리마켓 LOC 타깃 미국 거래일 = KST 당일."""
        return TossClient.target_us_date_for_morning_job(kst_now)

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
            cal = self._get_us_market_calendar_cached()
            return self._market_status_from_calendar(cal.get("today", {}))
        except Exception:
            return self._market_status_fallback()
