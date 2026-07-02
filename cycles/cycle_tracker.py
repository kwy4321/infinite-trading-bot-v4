"""무한매수 회차(사이클) 추적."""

import datetime
import os
import random
import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional, Union

from config.json_io import load_json, save_json
from config.settings import SYMBOLS, get_settings

CYCLES_FILE = "cycles.json"
DEFAULT_DATA = os.path.join("data", "accounts", "default")


def _today_str() -> str:
    return datetime.date.today().isoformat()


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
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_all(self) -> dict:
        with self._lock:
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
        # 회차 '시작일'은 레코드 생성일이 아니라 실제 첫 매수일로 기록한다.
        if cur.get("buy_count", 0) == 0 and cur.get("total_buy_usd", 0.0) == 0:
            cur["started_at"] = _today_str()
        cur["total_buy_usd"] = round(cur["total_buy_usd"] + max(0.0, usd_amount), 2)
        cur["buy_count"] = cur.get("buy_count", 0) + 1
        cur["max_T"] = max(cur.get("max_T", 0.0), float(t_after))
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
            "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
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

    def portfolio_stats(self) -> dict:
        data = self._load_all()
        realized_usd = 0.0
        completed_cycles = 0
        active_cycles = 0
        per_symbol = {}
        for sym in SYMBOLS:
            s = self._get(data, sym)
            sym_realized = sum(c.get("profit_usd", 0.0) for c in s.get("completed", []))
            sym_completed = len(s.get("completed", []))
            sym_active = 1 if s.get("current") else 0
            realized_usd += sym_realized
            completed_cycles += sym_completed
            active_cycles += sym_active
            per_symbol[sym] = {
                "realized_usd": round(sym_realized, 2),
                "completed_cycles": sym_completed,
                "active": bool(sym_active),
            }
        return {
            "realized_usd": round(realized_usd, 2),
            "completed_cycles": completed_cycles,
            "active_cycles": active_cycles,
            "per_symbol": per_symbol,
        }

    def format_cycles_report(self, symbol: str, qty: int, avg_price: float, current_price: float) -> str:
        sym = self.get_symbol_data(symbol)
        lines = [f"📒 <b>[{symbol}] 회차 기록</b>\n"]
        snap = sym.get("current", {}).get("snapshot") if sym.get("current") else None
        live = self.calc_unrealized_pnl(symbol, qty, avg_price, current_price)
        if live:
            sign = "+" if live["cycle_pnl_usd"] >= 0 else ""
            lines += [
                f"🔵 <b>진행 중 — {live['cycle_no']}회차</b>",
                f"  시작: {live['started_at']}",
            ]
            if snap:
                lines += [
                    f"  🎯 T <b>{snap['T']:g}</b> · 평단 <b>${snap['avg_price']:,.2f}</b> · <b>{snap['qty']}</b>주",
                    f"  💵 평가금액 <b>${snap['eval_usd']:,.2f}</b> (투입 ${snap['invested_usd']:,.2f})",
                ]
            lines += [
                f"  회차 손익: {sign}${live['cycle_pnl_usd']:,.2f} ({sign}{live['cycle_pnl_pct']:.2f}%)", "",
            ]
        else:
            lines.append("💤 진행 중인 회차 없음\n")
        completed = sym.get("completed", [])
        if completed:
            lines.append(f"🏆 <b>완료 ({len(completed)}개)</b>")
            for c in reversed(completed[-10:]):
                sign = "+" if c["profit_usd"] >= 0 else ""
                lines.append(f"  #{c['cycle_no']} {c['ended_at']} | {sign}${c['profit_usd']:,.2f} ({sign}{c['profit_pct']:.2f}%)")
        else:
            lines.append("📭 완료된 회차 없음")
        if snap and snap.get("at"):
            snap_at = snap["at"][:16].replace("T", " ")
            lines.append(f"\n<i>🔄 {snap_at} 동기화</i>")
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
            bar = "🟩" if info["profit_usd"] >= 0 else "🟥"
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

        note = completed.get("note", "")
        note_line = f"\n📝 <i>{note}</i>" if note else ""
        dot = "🟢" if usd >= 0 else "🔴"

        card = (
            f"◆ <b>{symbol}</b>　·　🔢 <b>{completed['cycle_no']}회차</b>\n"
            f"📅 <i>{completed['started_at']} → {completed['ended_at']}</i>\n"
            f"🔁 <i>{trades}번 매매</i>\n"
            f"{dot} <b>{sign}${usd:,.2f}</b>　<i>({sign}{pct:.2f}%)</i>{note_line}"
        )

        return (
            f"<b>{headline}</b>\n"
            f"<blockquote>{card}</blockquote>\n"
            f"<i>{tagline}</i>"
        )
