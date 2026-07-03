"""토스 CLOSED 주문 orderedAt 확인 — 매매날짜 디버그용.

서버 실행:
  bash scripts/inspect_broker_fills.sh SOXL
  # 또는
  .venv/bin/python scripts/inspect_broker_fills.py SOXL
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, val = text.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:
    _load_env_file(ROOT / ".env")

from account.account import AccountPaths
from broker.rate_limiter import RateLimiter
from broker.toss_auth import TossAuth
from broker.toss_client import TossClient
from cycles.cycle_tracker import _trade_date_display


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    symbol = (sys.argv[1] if len(sys.argv) > 1 else "SOXL").upper()
    client_id = os.getenv("TOSS_CLIENT_ID", "").strip()
    client_secret = os.getenv("TOSS_CLIENT_SECRET", "").strip()
    account_seq = os.getenv("TOSS_ACCOUNT_SEQ", "1").strip()
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    if dry_run or not client_id or not client_secret:
        print("DRY_RUN=false 및 TOSS 키 필요")
        return 1

    paths = AccountPaths()
    auth = TossAuth(client_id, client_secret, paths.token_cache, RateLimiter())
    broker = TossClient(auth, account_seq, RateLimiter(), dry_run=False)

    fills = broker.list_broker_fills(symbol, days=90, max_orders=50)
    pos = broker.get_holdings_item(symbol)
    qty = int(pos.get("qty", 0) or 0)
    selected = __import__("cycles.cycle_tracker", fromlist=["CycleTracker"]).CycleTracker.select_position_fills(
        fills, qty,
    )

    print(f"=== {symbol} 보유 {qty}주 ===")
    print(f"CLOSED 체결 {len(fills)}건, 현재 포지션 설명 {len(selected)}건\n")
    for i, f in enumerate(selected, 1):
        raw = f.get("ordered_at") or f.get("filled_at") or ""
        print(
            f"{i}. {_trade_date_display(raw)} | {f.get('side')} {f.get('qty')}주 "
            f"@ ${f.get('price')} | orderedAt={raw} | id={str(f.get('order_id', ''))[:16]}…"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
