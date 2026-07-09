"""무한매수 회차(사이클) 추적."""

from __future__ import annotations

import datetime
import os
import random
import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional, Union
from zoneinfo import ZoneInfo

from config.json_io import load_json, save_json
from config.settings import SYMBOLS, get_settings

CYCLES_FILE = "cycles.json"
DEFAULT_DATA = os.path.join("data", "accounts", "default")
KST = ZoneInfo("Asia/Seoul")


def _parse_trade_dt(raw: str) -> datetime.datetime | None:
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _today_str() -> str:
    return datetime.datetime.now(KST).date().isoformat()


def _trade_date_display(raw_when: str) -> str:
    """주문 접수 시각 → KST 날짜 (토스 주문내역과 동일)."""
    if not raw_when:
        return "—"
    text = str(raw_when).strip()
    if len(text) == 10 and text[4] == "-" and "T" not in text:
        return text
    dt = _parse_trade_dt(text)
    if not dt:
        return text[:10] if len(text) >= 10 else "—"
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def _default_symbol_data() -> dict:
    return {"current": None, "completed": [], "next_cycle_no": 1}


def _new_current(cycle_no: int, principal: float) -> dict:
    return {
        "cycle_no": cycle_no,
        "started_at": _today_str(),
        "principal": round(float(principal), 2),
        "total_buy_usd": 0.0,
        "total_sell_usd": 0.0,
        "max_T": 0.0,
        "buy_count": 0,
        "sell_count": 0,
    }


class CycleTracker:
    def __init__(self, data_dir: Union[str, Path] = DEFAULT_DATA):
        self.data_dir = str(data_dir)
        self.path = os.path.join(self.data_dir, CYCLES_FILE)
        self._lock = threading.RLock()
        self._batch_data: dict | None = None
        self._batch_dirty = False
        os.makedirs(self.data_dir, exist_ok=True)

    def batch(self):
        """여러 cycle 갱신을 cycles.json 1회 저장으로 묶는다."""
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            with self._lock:
                self._batch_data = self._load_all()
                self._batch_dirty = False
            try:
                yield
            finally:
                with self._lock:
                    if self._batch_dirty and self._batch_data is not None:
                        self._trim_completed(self._batch_data)
                        save_json(Path(self.path), self._batch_data, compact=True)
                    self._batch_data = None
                    self._batch_dirty = False

        return _ctx()

    def _load_all(self) -> dict:
        with self._lock:
            if self._batch_data is not None:
                return self._batch_data
            default = {s: _default_symbol_data() for s in SYMBOLS}
            if not os.path.exists(self.path):
                return default
            data = load_json(Path(self.path), {})
            if not isinstance(data, dict):
                data = {}
            for s in SYMBOLS:
                if s not in data:
                    data[s] = _default_symbol_data()
                else:
                    base = _default_symbol_data()
                    base.update(data[s])
                    data[s] = base
            return data

    def _trim_completed(self, data: dict) -> None:
        limit = get_settings().max_completed_cycles
        for s in SYMBOLS:
            sym = self._get(data, s)
            completed = sym.get("completed", [])
            if len(completed) > limit:
                sym["completed"] = completed[-limit:]

    def _save_all(self, data: dict) -> None:
        with self._lock:
            if self._batch_data is not None:
                self._batch_data = data
                self._batch_dirty = True
                return
            self._trim_completed(data)
            save_json(Path(self.path), data, compact=True)

    def _get(self, data: dict, symbol: str) -> dict:
        symbol = symbol.upper()
        if symbol not in data:
            data[symbol] = _default_symbol_data()
        return data[symbol]

    def ensure_current(self, symbol: str, principal: float) -> dict:
        data = self._load_all()
        sym = self._get(data, symbol)
        if sym["current"] is None:
            sym["current"] = _new_current(sym["next_cycle_no"], principal)
        self._save_all(data)
        return sym["current"]

    def record_buy(self, symbol: str, usd_amount: float, t_after: float, principal: float) -> None:
        data = self._load_all()
        sym = self._get(data, symbol)
        if sym["current"] is None:
            sym["current"] = _new_current(sym["next_cycle_no"], principal)
        cur = sym["current"]
        # record_trade에서 첫 매수 체결일로 started_at 설정
        cur["total_buy_usd"] = round(cur["total_buy_usd"] + max(0.0, usd_amount), 2)
        cur["buy_count"] = cur.get("buy_count", 0) + 1
        cur["max_T"] = max(cur.get("max_T", 0.0), float(t_after))
        self._save_all(data)

    def record_trade(
        self,
        symbol: str,
        *,
        side: str,
        qty: int,
        price: float,
        action: str | None,
        t_before: float,
        t_after: float,
        avg_after: float,
        qty_after: int,
        source: str,
        note: str = "",
        order_id: str | None = None,
        fill_id: str | None = None,
        filled_at: str | None = None,
    ) -> None:
        """현재 회차 매매 내역 기록 (체결 동기화·봇 주문 공통)."""
        data = self._load_all()
        sym = self._get(data, symbol)
        if sym["current"] is None:
            return
        cur = sym["current"]
        trades = cur.setdefault("trades", [])
        when = filled_at or datetime.datetime.now(KST).isoformat(timespec="seconds")
        if side.upper() == "BUY" and not trades:
            cur["started_at"] = _trade_date_display(when)
        trades.append({
            "symbol": symbol.upper(),
            "side": side.upper(),
            "qty": int(qty),
            "price": round(float(price), 2),
            "avg_after": round(float(avg_after), 4),
            "qty_after": int(qty_after),
            "action": action,
            "t_before": round(float(t_before), 2),
            "t_after": round(float(t_after), 2),
            "source": source,
            "note": note,
            "order_id": order_id,
            "fill_id": fill_id,
            "ordered_at": when,
            "filled_at": when,
            "at": when,
        })
        cur["trades"] = self._dedupe_trades(trades)[-100:]
        self._save_all(data)

    def record_sell(self, symbol: str, usd_amount: float, t_after: float,
                    qty_after: int, principal: float) -> Optional[dict]:
        data = self._load_all()
        sym = self._get(data, symbol)
        if sym["current"] is None:
            sym["current"] = _new_current(sym["next_cycle_no"], principal)
        cur = sym["current"]
        cur["total_sell_usd"] = round(cur["total_sell_usd"] + max(0.0, usd_amount), 2)
        cur["sell_count"] = cur.get("sell_count", 0) + 1
        cur["max_T"] = max(cur.get("max_T", 0.0), float(t_after))
        self._save_all(data)
        if int(qty_after) <= 0:
            return self.complete_cycle(symbol)
        return None

    def complete_cycle(self, symbol: str, note: str = "") -> Optional[dict]:
        data = self._load_all()
        sym = self._get(data, symbol)
        cur = sym["current"]
        if cur is None:
            return None
        buy = cur["total_buy_usd"]
        sell = cur["total_sell_usd"]
        profit = round(sell - buy, 2)
        pct = round((profit / buy * 100), 2) if buy > 0 else 0.0
        completed = {
            "cycle_no": cur["cycle_no"],
            "started_at": cur["started_at"],
            "ended_at": _today_str(),
            "principal": cur["principal"],
            "total_buy_usd": buy,
            "total_sell_usd": sell,
            "profit_usd": profit,
            "profit_pct": pct,
            "max_T": cur.get("max_T", 0.0),
            "buy_count": cur.get("buy_count", 0),
            "sell_count": cur.get("sell_count", 0),
            "trades": list(cur.get("trades") or []),
            "note": note,
        }
        sym["completed"].append(completed)
        sym["next_cycle_no"] = cur["cycle_no"] + 1
        sym["current"] = None
        self._save_all(data)
        return completed

    def record_snapshot(self, symbol: str, *, t_val: float, avg_price: float,
                        qty: int, current_price: float, eval_usd: float,
                        invested_usd: float, principal: float) -> dict:
        """토스 실계좌 기준 현재 진행 회차 스냅샷 기록 (T·평단가·주수·평가금액)."""
        data = self._load_all()
        sym = self._get(data, symbol)
        if sym["current"] is None:
            sym["current"] = _new_current(sym["next_cycle_no"], principal)
        snapshot = {
            "T": round(float(t_val), 2),
            "avg_price": round(float(avg_price), 4),
            "qty": int(qty),
            "current_price": round(float(current_price), 4),
            "eval_usd": round(float(eval_usd), 2),
            "invested_usd": round(float(invested_usd), 2),
            "at": datetime.datetime.now(KST).isoformat(timespec="seconds"),
        }
        sym["current"]["snapshot"] = snapshot
        self._save_all(data)
        return snapshot

    def get_symbol_data(self, symbol: str) -> dict:
        return self._get(self._load_all(), symbol)

    def calc_unrealized_pnl(self, symbol: str, qty: int, avg_price: float, current_price: float) -> dict:
        sym = self.get_symbol_data(symbol)
        cur = sym["current"]
        if cur is None:
            return {}
        buy = cur["total_buy_usd"]
        sell = cur["total_sell_usd"]
        position_value = qty * current_price if qty > 0 and current_price > 0 else 0.0
        cycle_pnl = round(sell + position_value - buy, 2)
        cycle_pct = round((cycle_pnl / buy * 100), 2) if buy > 0 else 0.0
        unrealized = round(position_value - qty * avg_price, 2) if qty > 0 else 0.0
        return {
            "cycle_no": cur["cycle_no"], "started_at": cur["started_at"],
            "total_buy_usd": buy, "total_sell_usd": sell,
            "cycle_pnl_usd": cycle_pnl, "cycle_pnl_pct": cycle_pct,
            "unrealized_usd": unrealized, "max_T": cur.get("max_T", 0.0),
        }

    def monthly_summary(self, symbol: Optional[str] = None, year: Optional[int] = None) -> dict:
        year = year or datetime.date.today().year
        data = self._load_all()
        symbols = [symbol.upper()] if symbol else list(SYMBOLS)
        months = defaultdict(lambda: {"cycles": 0, "profit_usd": 0.0, "buy_usd": 0.0, "details": []})
        for sym in symbols:
            for c in self._get(data, sym).get("completed", []):
                ended = c.get("ended_at", "")[:7]
                if not ended.startswith(str(year)):
                    continue
                months[ended]["cycles"] += 1
                months[ended]["profit_usd"] += c.get("profit_usd", 0.0)
                months[ended]["buy_usd"] += c.get("total_buy_usd", 0.0)
                months[ended]["details"].append({**c, "symbol": sym})
        result = {}
        for m in sorted(months.keys()):
            info = months[m]
            buy = info["buy_usd"]
            profit = round(info["profit_usd"], 2)
            pct = round((profit / buy * 100), 2) if buy > 0 else 0.0
            result[m] = {"cycles": info["cycles"], "profit_usd": profit, "profit_pct_on_buy": pct, "details": info["details"]}
        return result

    def cycle_progress(self, symbol: str, *, trading: bool, qty: int) -> int:
        """거래 종목이 아니면 0. 매수 시작 전이면 0. 진행 중이면 cycle_no."""
        if not trading:
            return 0
        cur = self.get_symbol_data(symbol).get("current")
        if not cur:
            return 0
        if qty <= 0 and cur.get("buy_count", 0) == 0 and cur.get("total_buy_usd", 0) <= 0:
            return 0
        return int(cur.get("cycle_no", 1))

    def portfolio_stats(
        self,
        symbols: tuple | list | None = None,
        qty_by_symbol: dict | None = None,
    ) -> dict:
        syms = tuple(symbols) if symbols else SYMBOLS
        trading_set = {s.upper() for s in syms}
        qty_map = qty_by_symbol or {}
        data = self._load_all()
        realized_usd = 0.0
        completed_cycles = 0
        active_cycles = 0
        active_cycle_nos: list[int] = []
        per_symbol = {}
        for sym in SYMBOLS:
            s = self._get(data, sym)
            is_trading = sym in trading_set
            qty = int(qty_map.get(sym, 0))
            progress = self.cycle_progress(sym, trading=is_trading, qty=qty)
            cur = s.get("current")
            sym_realized = sum(c.get("profit_usd", 0.0) for c in s.get("completed", []))
            sym_completed = len(s.get("completed", []))
            if is_trading:
                realized_usd += sym_realized
                completed_cycles += sym_completed
                if progress > 0:
                    active_cycles += 1
                    active_cycle_nos.append(progress)
            per_symbol[sym] = {
                "realized_usd": round(sym_realized, 2) if is_trading else 0.0,
                "completed_cycles": sym_completed if is_trading else 0,
                "active": progress > 0,
                "cycle_progress": progress,
                "cycle_no": int(cur["cycle_no"]) if cur else None,
            }
        unique_nos = sorted(set(active_cycle_nos))
        if len(unique_nos) == 1:
            active_cycle_label = str(unique_nos[0])
        elif unique_nos:
            active_cycle_label = "/".join(str(n) for n in unique_nos)
        else:
            active_cycle_label = None
        return {
            "realized_usd": round(realized_usd, 2),
            "completed_cycles": completed_cycles,
            "active_cycles": active_cycles,
            "active_cycle_label": active_cycle_label,
            "per_symbol": per_symbol,
        }

    @classmethod
    def _trade_dedup_key(cls, tr: dict) -> str:
        oid = str(tr.get("order_id") or "").strip()
        if oid:
            return f"oid:{oid}"
        fid = str(tr.get("fill_id") or "").strip()
        if fid:
            return f"fid:{fid}"
        when = tr.get("ordered_at") or tr.get("filled_at") or tr.get("at") or ""
        t_after = tr.get("t_after")
        t_before = tr.get("t_before")
        return "|".join([
            str(tr.get("side", "")).upper(),
            str(int(tr.get("qty", 0))),
            f"{float(tr.get('price', 0)):.2f}",
            "" if t_before in (None, "") else f"{float(t_before):g}",
            "" if t_after in (None, "") else f"{float(t_after):g}",
            str(when)[:19],
        ])

    @classmethod
    def _dedupe_trades(cls, trades: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for tr in sorted(trades, key=cls._trade_sort_key):
            key = cls._trade_dedup_key(tr)
            if key in seen:
                continue
            seen.add(key)
            out.append(tr)
        return out

    @staticmethod
    def _trade_sort_key(tr: dict) -> str:
        return tr.get("ordered_at") or tr.get("filled_at") or tr.get("at") or ""

    @classmethod
    def _fill_log_to_trade(cls, symbol: str, entry: dict) -> dict:
        side = (entry.get("side") or "BUY").upper()
        price = float(entry.get("price", 0))
        return {
            "symbol": (entry.get("symbol") or symbol).upper(),
            "side": side,
            "qty": int(entry.get("qty", 0)),
            "price": round(price, 2),
            "avg_after": round(float(entry.get("avg_after", price)), 4),
            "qty_after": int(entry.get("qty_after", 0)),
            "action": entry.get("action"),
            "t_before": entry.get("t_before"),
            "t_after": entry.get("t_after"),
            "source": entry.get("source", "sync"),
            "ordered_at": entry.get("ordered_at") or entry.get("filled_at") or entry.get("at"),
            "filled_at": entry.get("ordered_at") or entry.get("filled_at") or entry.get("at"),
            "at": entry.get("ordered_at") or entry.get("filled_at") or entry.get("at"),
            "fill_id": entry.get("id"),
            "order_id": entry.get("order_id"),
        }

    @classmethod
    def _merge_trade(cls, existing: dict, incoming: dict) -> dict:
        """같은 체결 병합 — sync 추정일로 broker·기존 체결일 덮어쓰지 않음."""
        merged = {**existing, **incoming}
        in_when = incoming.get("ordered_at") or incoming.get("filled_at") or incoming.get("at") or ""
        ex_when = existing.get("ordered_at") or existing.get("filled_at") or existing.get("at") or ""
        in_src = str(incoming.get("source") or "")
        ex_src = str(existing.get("source") or "")
        if incoming.get("order_id") or in_src == "broker":
            if in_when:
                merged["ordered_at"] = in_when
                merged["filled_at"] = in_when
                merged["at"] = in_when
            in_price = incoming.get("price")
            if in_price not in (None, ""):
                merged["price"] = round(float(in_price), 2)
        elif in_src == "sync" and (ex_src == "broker" or existing.get("order_id")):
            merged["ordered_at"] = ex_when or in_when
            merged["filled_at"] = ex_when or in_when
            merged["at"] = ex_when or in_when
            if existing.get("price") not in (None, ""):
                merged["price"] = round(float(existing["price"]), 2)
        elif in_src == "sync" and ex_when:
            merged["ordered_at"] = ex_when
            merged["filled_at"] = ex_when
            merged["at"] = ex_when
        elif in_when and not ex_when:
            merged["ordered_at"] = in_when
            merged["filled_at"] = in_when
            merged["at"] = in_when
        elif ex_when:
            merged["ordered_at"] = ex_when
            merged["filled_at"] = ex_when
            merged["at"] = ex_when
        for key in ("order_id", "fill_id", "source", "note"):
            val = incoming.get(key)
            if val not in (None, ""):
                merged[key] = val
        return merged

    @classmethod
    def apply_broker_fill_dates(cls, records: list[dict], broker_fills: list[dict]) -> int:
        """토스 체결 목록과 매칭해 filled_at·order_id 보정. 갱신 건수 반환."""
        if not records or not broker_fills:
            return 0
        used: set[str] = set()
        updated = 0

        def mark(rec: dict, fill: dict) -> None:
            nonlocal updated
            when = fill.get("ordered_at") or fill.get("filled_at") or ""
            rec["ordered_at"] = when
            rec["filled_at"] = when
            rec["at"] = when
            rec["order_id"] = fill["order_id"]
            rec["price"] = round(float(fill.get("price") or rec.get("price") or 0), 2)
            used.add(fill["order_id"])
            updated += 1

        for rec in records:
            oid = str(rec.get("order_id") or "")
            if not oid:
                continue
            for fill in broker_fills:
                if fill["order_id"] == oid and oid not in used:
                    mark(rec, fill)
                    break

        for rec in records:
            if str(rec.get("order_id") or "") in used:
                continue
            side = str(rec.get("side") or "").upper()
            qty = int(rec.get("qty") or 0)
            price = float(rec.get("price") or 0)
            best = None
            best_diff = None
            for fill in broker_fills:
                if fill["order_id"] in used:
                    continue
                if fill["side"] != side or fill["qty"] != qty:
                    continue
                diff = abs(fill["price"] - price)
                if diff > max(0.15, price * 0.03):
                    continue
                if best is None or diff < best_diff:
                    best = fill
                    best_diff = diff
            if best:
                mark(rec, best)

        pools: dict[tuple[str, int], list[dict]] = {}
        for fill in broker_fills:
            if fill["order_id"] in used:
                continue
            key = (fill["side"], fill["qty"])
            pools.setdefault(key, []).append(fill)
        for key in pools:
            pools[key].sort(key=lambda f: f.get("ordered_at") or f.get("filled_at") or "")

        remaining = [
            r for r in records
            if str(r.get("order_id") or "") not in used
        ]
        remaining.sort(
            key=lambda r: (
                str(r.get("side") or ""),
                float(r.get("t_after") if r.get("t_after") not in (None, "") else r.get("t_before") or 0),
                float(r.get("price") or 0),
            )
        )
        for rec in remaining:
            key = (str(rec.get("side") or "").upper(), int(rec.get("qty") or 0))
            pool = pools.get(key) or []
            if not pool:
                continue
            mark(rec, pool.pop(0))

        return updated

    @classmethod
    def select_position_fills(cls, broker_fills: list[dict], target_qty: int) -> list[dict]:
        """현재 보유 수량을 설명하는 체결만 시간순 반환."""
        if target_qty <= 0 or not broker_fills:
            return []
        sorted_fills = sorted(
            broker_fills,
            key=lambda f: f.get("ordered_at") or f.get("filled_at") or "",
        )
        net = 0
        selected: list[dict] = []
        for fill in reversed(sorted_fills):
            side = str(fill.get("side") or "").upper()
            qty = int(fill.get("qty") or 0)
            if qty <= 0:
                continue
            if side == "BUY":
                net += qty
            elif side == "SELL":
                net -= qty
            else:
                continue
            selected.append(fill)
            if net >= target_qty:
                break
        selected.reverse()
        if net == target_qty:
            return selected
        buys = [f for f in sorted_fills if str(f.get("side") or "").upper() == "BUY"]
        total = 0
        out: list[dict] = []
        for fill in buys:
            out.append(fill)
            total += int(fill.get("qty") or 0)
            if total >= target_qty:
                break
        return out if total >= target_qty else selected

    @staticmethod
    def _recompute_cycle_totals_from_trades(cur: dict) -> None:
        """trades 체결가 기준으로 total_buy_usd·total_sell_usd 재계산."""
        buy_usd = sell_usd = 0.0
        buy_count = sell_count = 0
        for tr in cur.get("trades") or []:
            side = str(tr.get("side") or "").upper()
            qty = int(tr.get("qty") or 0)
            price = float(tr.get("price") or 0)
            usd = round(price * qty, 2)
            if side == "BUY":
                buy_usd += usd
                buy_count += 1
            elif side == "SELL":
                sell_usd += usd
                sell_count += 1
        cur["total_buy_usd"] = round(buy_usd, 2)
        cur["total_sell_usd"] = round(sell_usd, 2)
        cur["buy_count"] = buy_count
        cur["sell_count"] = sell_count

    def rebuild_trades_from_broker(
        self,
        symbol: str,
        broker_fills: list[dict],
        fill_log: list[dict],
        target_qty: int,
    ) -> int:
        """토스 체결(orderedAt) 기준으로 current.trades 재구성 — fill_log에서 T·action 보존."""
        fills = self.select_position_fills(broker_fills, target_qty)
        if not fills:
            return 0
        log_by_oid: dict[str, dict] = {}
        for entry in fill_log or []:
            oid = str(entry.get("order_id") or "").strip()
            if oid:
                log_by_oid[oid] = entry
        new_trades: list[dict] = []
        for fill in fills:
            oid = str(fill.get("order_id") or "").strip()
            entry = log_by_oid.get(oid)
            when = fill.get("ordered_at") or fill.get("filled_at") or ""
            tr: dict = {
                "symbol": symbol.upper(),
                "side": str(fill.get("side") or "").upper(),
                "qty": int(fill.get("qty") or 0),
                "price": round(float(fill.get("price") or 0), 2),
                "ordered_at": when,
                "filled_at": when,
                "at": when,
                "order_id": oid or None,
                "source": "broker",
            }
            if entry:
                tr["fill_id"] = entry.get("id")
                tr["action"] = entry.get("action")
                tr["t_before"] = entry.get("t_before")
                tr["t_after"] = entry.get("t_after")
                tr["avg_after"] = entry.get("avg_after")
                tr["qty_after"] = entry.get("qty_after")
                if entry.get("note"):
                    tr["note"] = entry.get("note")
            new_trades.append(tr)
        data = self._load_all()
        sym = self._get(data, symbol)
        cur = sym.get("current")
        if not cur:
            return 0
        cur["trades"] = new_trades
        self._recompute_cycle_totals_from_trades(cur)
        self._update_cycle_started_at(cur)
        self._save_all(data)
        return len(new_trades)

    @classmethod
    def _update_cycle_started_at(cls, cur: dict) -> None:
        buy_dates = [
            _trade_date_display(t.get("ordered_at") or t.get("filled_at") or t.get("at") or "")
            for t in cur.get("trades") or []
            if t.get("side") == "BUY"
            and _trade_date_display(t.get("ordered_at") or t.get("filled_at") or t.get("at") or "") != "—"
        ]
        if buy_dates:
            cur["started_at"] = min(buy_dates)

    @classmethod
    def _collect_trades(cls, sym_data: dict, symbol: str, fill_log: list | None = None) -> list[dict]:
        """현재 회차 매매 내역 — 저장된 trades 우선 (fill_log 병합으로 날짜 덮어쓰지 않음)."""
        stored = list((sym_data.get("current") or {}).get("trades") or [])
        if stored:
            return cls._dedupe_trades(stored)
        by_key: dict[str, dict] = {}
        for tr in stored:
            key = cls._trade_dedup_key(tr)
            by_key[key] = tr
        for entry in fill_log or []:
            tr = cls._fill_log_to_trade(symbol, entry)
            key = cls._trade_dedup_key(tr)
            if key in by_key:
                by_key[key] = cls._merge_trade(by_key[key], tr)
            else:
                by_key[key] = tr
        return cls._dedupe_trades(list(by_key.values()))

    @classmethod
    def display_trades_from_broker(
        cls,
        symbol: str,
        broker_fills: list[dict],
        sym_data: dict,
        fill_log: list[dict] | None,
        target_qty: int,
    ) -> list[dict]:
        """텔레그램 표시용 — broker 체결가·날짜 + cycles/fill_log T·action."""
        fills = cls.select_position_fills(broker_fills, target_qty)
        if not fills:
            return cls._collect_trades(sym_data, symbol, fill_log)
        log_by_oid: dict[str, dict] = {}
        for entry in fill_log or []:
            oid = str(entry.get("order_id") or "").strip()
            if oid:
                log_by_oid[oid] = entry
        stored_by_oid: dict[str, dict] = {}
        for tr in (sym_data.get("current") or {}).get("trades") or []:
            oid = str(tr.get("order_id") or "").strip()
            if oid:
                stored_by_oid[oid] = tr
        out: list[dict] = []
        for fill in fills:
            oid = str(fill.get("order_id") or "").strip()
            when = fill.get("ordered_at") or fill.get("filled_at") or ""
            tr: dict = {
                "symbol": symbol.upper(),
                "side": str(fill.get("side") or "").upper(),
                "qty": int(fill.get("qty") or 0),
                "price": round(float(fill.get("price") or 0), 2),
                "ordered_at": when,
                "filled_at": when,
                "at": when,
                "order_id": oid or None,
                "source": "broker",
            }
            meta = log_by_oid.get(oid) or stored_by_oid.get(oid)
            if meta:
                for key in (
                    "fill_id", "action", "t_before", "t_after",
                    "avg_after", "qty_after", "note",
                ):
                    if meta.get(key) not in (None, ""):
                        tr[key] = meta[key]
            out.append(tr)
        return cls._dedupe_trades(out)

    def sync_trades_from_fill_log(self, symbol: str, fill_log: list, principal: float) -> None:
        """fill_log → cycles.current.trades 영구 반영 + 중복 정리."""
        data = self._load_all()
        sym = self._get(data, symbol)
        if sym["current"] is None:
            if not fill_log:
                return
            sym["current"] = _new_current(sym["next_cycle_no"], principal)
        cur = sym["current"]
        trades = list(cur.get("trades") or [])
        by_key = {self._trade_dedup_key(t): i for i, t in enumerate(trades)}
        for entry in fill_log or []:
            tr = self._fill_log_to_trade(symbol, entry)
            key = self._trade_dedup_key(tr)
            if key in by_key:
                idx = by_key[key]
                trades[idx] = self._merge_trade(trades[idx], tr)
                continue
            trades.append(tr)
            by_key[key] = len(trades) - 1
        cur["trades"] = self._dedupe_trades(trades)[-100:]
        self._save_all(data)

    def reconcile_trade_dates(self, symbol: str, broker_fills: list[dict]) -> int:
        """토스 체결 목록으로 current.trades 날짜·order_id 재매칭."""
        if not broker_fills:
            return 0
        data = self._load_all()
        sym = self._get(data, symbol)
        cur = sym.get("current")
        if not cur:
            return 0
        trades = list(cur.get("trades") or [])
        n = self.apply_broker_fill_dates(trades, broker_fills)
        cur["trades"] = trades
        if n:
            self._update_cycle_started_at(cur)
        self._save_all(data)
        return n

    def dedupe_symbol_trades(self, symbol: str) -> None:
        """저장된 매매 내역 중복 제거."""
        data = self._load_all()
        sym = self._get(data, symbol)
        cur = sym.get("current")
        if not cur:
            return
        trades = cur.get("trades") or []
        cur["trades"] = self._dedupe_trades(trades)[-100:]
        self._save_all(data)

    @classmethod
    def format_trade_line(
        cls, symbol: str, tr: dict, *, index: int | None = None, side_style: str = "arrow",
    ) -> str:
        """매매 1건 — 연번 · 날짜 · 종목 · 매수/매도 · 수량 · 체결가 · 합계 · T (한 줄)."""
        side = tr.get("side", "")
        sym = tr.get("symbol") or symbol
        from tg.ui import side_icon
        icon = side_icon(side, style=side_style)
        side_txt = "매수" if side == "BUY" else "매도"
        side_part = f"{icon}{side_txt}" if icon else side_txt
        raw_when = tr.get("ordered_at") or tr.get("filled_at") or tr.get("at") or ""
        when = _trade_date_display(raw_when)
        qty = int(tr.get("qty", 0))
        exec_price = float(tr.get("price") or 0)
        total_usd = round(exec_price * qty, 2)
        t_after = tr.get("t_after")
        t_before = tr.get("t_before")
        if t_before not in (None, "") and float(t_before) != float(t_after or 0):
            t_txt = f"T {float(t_before):g}→{float(t_after):g}"
        elif t_after not in (None, ""):
            t_txt = f"T {float(t_after):g}"
        else:
            t_txt = "T —"
        prefix = f"<b>{index}.</b> " if index is not None else ""
        if qty > 1:
            amt_txt = f"${exec_price:,.2f} · 합 ${total_usd:,.2f}"
        else:
            amt_txt = f"${exec_price:,.2f}"
        return (
            f"{prefix}{when} · <b>{sym}</b> · {side_part} · "
            f"<b>{qty}</b>주 · {amt_txt} · {t_txt}"
        )

    @classmethod
    def format_trade_block(cls, symbol: str, trades: list[dict]) -> list[str]:
        """매매 내역 블록 — 연번 + 줄 간격."""
        if not trades:
            return []
        from tg.ui import dim
        lines = [f"  {dim('매매 내역')}", ""]
        shown = trades[-20:]
        start_no = max(1, len(trades) - len(shown) + 1)
        for i, tr in enumerate(shown):
            lines.append(f"  {cls.format_trade_line(symbol, tr, index=start_no + i)}")
            if i < len(shown) - 1:
                lines.append("")
        lines.append("")
        return lines

    def format_cycles_report(
        self,
        symbol: str,
        qty: int,
        avg_price: float,
        current_price: float,
        fill_log: list | None = None,
        *,
        broker_fills: list[dict] | None = None,
    ) -> str:
        sym = self.get_symbol_data(symbol)
        from tg.ui import dim, pnl_line, trend_arrow
        lines = [f"♾️ <b>[{symbol}] 회차 기록</b>\n"]
        snap = sym.get("current", {}).get("snapshot") if sym.get("current") else None
        live = self.calc_unrealized_pnl(symbol, qty, avg_price, current_price)
        if broker_fills and qty > 0:
            trades = self.display_trades_from_broker(
                symbol, broker_fills, sym, fill_log, qty,
            )
        else:
            trades = self._collect_trades(sym, symbol, fill_log)

        if live:
            lines += [
                f"<b>진행 중 — {live['cycle_no']}회차</b>",
                f"  {dim('시작')} {live['started_at']}",
            ]
            if snap:
                lines += [
                    f"  {dim('T')} <b>{snap['T']:g}</b> · {dim('평단')} <b>${snap['avg_price']:,.2f}</b> · <b>{snap['qty']}</b>주",
                    f"  {dim('평가')} <b>${snap['eval_usd']:,.2f}</b> ({dim('투입')} ${snap['invested_usd']:,.2f})",
                ]
            lines += [
                f"  {dim('회차 손익')} {pnl_line(live['cycle_pnl_usd'], live['cycle_pnl_pct'])}", "",
            ]
        elif qty > 0 or trades:
            cycle_no = (sym.get("current") or {}).get("cycle_no", 1)
            lines += [
                f"<b>진행 중 — {cycle_no}회차</b>",
                f"  {dim('T')} · {dim('평단')} <b>${avg_price:,.2f}</b> · <b>{qty}</b>주", "",
            ]
        else:
            lines.append(f"{dim('진행 중인 회차 없음')}\n")

        if trades:
            lines.extend(self.format_trade_block(symbol, trades))

        completed = sym.get("completed", [])
        if completed:
            lines.append(f"🏆 <b>완료된 회차 ({len(completed)}개)</b>")
            lines.append("")
            for c in reversed(completed[-10:]):
                sign = "+" if c["profit_usd"] >= 0 else ""
                lines.append(
                    f"  #{c['cycle_no']} {c['ended_at']} · "
                    f"{trend_arrow(c['profit_usd'] >= 0)} {sign}${c['profit_usd']:,.2f} ({sign}{c['profit_pct']:.2f}%)"
                )
                c_trades = self._dedupe_trades(c.get("trades") or [])
                for j, tr in enumerate(c_trades[-10:], 1):
                    lines.append(f"  {self.format_trade_line(symbol, tr, index=j)}")
                lines.append("")
        elif not trades:
            lines.append("📭 매매·완료 회차 기록 없음")
        if snap and snap.get("at"):
            snap_at = _trade_date_display(snap["at"])
            lines.append(f"\n<i>{dim('동기화')} {snap_at}</i>")
        return "\n".join(lines)

    def format_monthly_report(self, year: Optional[int] = None, symbol: Optional[str] = None) -> str:
        year = year or datetime.date.today().year
        label = symbol or "전체"
        summary = self.monthly_summary(symbol, year)
        lines = [f"📅 <b>[{label}] {year}년 월별 수익</b>\n"]
        if not summary:
            lines.append("해당 연도 완료 회차가 없습니다.")
            return "\n".join(lines)
        for month, info in summary.items():
            mm = month[5:7]
            sign = "+" if info["profit_usd"] >= 0 else ""
            bar = "▲" if info["profit_usd"] >= 0 else "▼"
            lines.append(f"{bar} <b>{mm}월</b> | {info['cycles']}회 | {sign}${info['profit_usd']:,.2f} ({sign}{info['profit_pct_on_buy']:.2f}%)")
        return "\n".join(lines)

    _GRADUATION_VARIANTS = (
        (15, (
            ("🎉🚀  대졸업!", "라오어가 눈물 흘리며 박수칩니다 👏✨"),
            ("🏆✨  만점 졸업!", "무한매수 교과서에 올릴 한 사이클 📖🔥"),
            ("🎊🚀  대졸업!", "오늘 저녁은 스테이크 각 🥩🍾"),
        )),
        (5, (
            ("🎓✨  졸업!", "깔끔하게 한 사이클 완주 🏁"),
            ("✅🎓  졸업!", "차분한 승리 — 다음 타자 대기 ⚾✨"),
            ("🎓  졸업!", "수익 실현 완료, 지갑이 한결 가벼워짐 💼😊"),
        )),
        (0, (
            ("🎓  졸업", "플러스 마감 — 다음 회차 가즈아 💪"),
            ("🎓  졸업", "0보다 크면 승리, 오늘도 이겼다 ✅"),
            ("📈🎓  졸업", "조금씩 쌓인 게 오늘 졸업장 🎓"),
        )),
        (-5, (
            ("🫠  졸업…", "살짝 아쉽지만, 무한매수는 무한이지 🔄"),
            ("🫠  졸업…", "손해는 수업료… 다음이 진짜다 📚"),
            ("😅🎓  졸업…", "마이너스 졸업도 졸업입니다 (?) 🎓"),
        )),
        (float("-inf"), (
            ("😤  회차 종료", "이번 판은 접고 리벤지 각 🔥"),
            ("💢  회차 종료", "실패는 데이터, 다음은 더 날카롭게 📉➡️📈"),
            ("⚔️  회차 종료", "회차 스킵 — 다음 사이클이 기다림 🔥"),
        )),
    )

    def format_graduation_message(self, completed: dict, symbol: str) -> str:
        pct = completed["profit_pct"]
        usd = completed["profit_usd"]
        sign = "+" if usd >= 0 else ""
        trades = completed.get("buy_count", 0) + completed.get("sell_count", 0)
        headline, tagline = self._GRADUATION_VARIANTS[-1][1][0]
        for threshold, variants in self._GRADUATION_VARIANTS:
            if pct >= threshold:
                headline, tagline = random.choice(variants)
                break

        from tg.ui import dim, trend_arrow
        note = completed.get("note", "")
        note_line = f"\n{dim(note)}" if note else ""

        card = (
            f"◆ <b>{symbol}</b>　·　<b>{completed['cycle_no']}회차</b>\n"
            f"{dim(completed['started_at'] + ' → ' + completed['ended_at'])}\n"
            f"{dim(str(trades) + '번 매매')}\n"
            f"{trend_arrow(usd >= 0)} <b>{sign}${usd:,.2f}</b>　<i>({sign}{pct:.2f}%)</i>{note_line}"
        )

        return (
            f"<b>{headline}</b>\n"
            f"<blockquote>{card}</blockquote>\n"
            f"<i>{tagline}</i>"
        )
