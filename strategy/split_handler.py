"""액면분할 수동 반영 (순수 계산)."""

def parse_ratio(text: str) -> float:
    text = text.strip().replace(" ", "")
    if ":" in text:
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError("비율 형식: 2:1 또는 1:2")
        a, b = float(parts[0]), float(parts[1])
        if b == 0:
            raise ValueError("분모는 0이 될 수 없습니다")
        return a / b
    ratio = float(text)
    if ratio <= 0:
        raise ValueError("비율은 0보다 커야 합니다")
    return ratio


def calc_adjustment(qty: int, avg_price: float, ratio: float) -> dict:
    if ratio <= 0 or qty < 0 or avg_price < 0:
        raise ValueError("잘못된 입력")
    new_qty = max(0, int(qty * ratio))
    new_avg = round(avg_price / ratio, 4) if ratio > 0 else avg_price
    return {
        "old_qty": qty, "old_avg": avg_price,
        "new_qty": new_qty, "new_avg": new_avg, "ratio": ratio,
    }


def apply_split(state: dict, ratio: float, note: str = "") -> dict:
    import datetime
    preview = calc_adjustment(int(state.get("qty", 0)), float(state.get("avg_price", 0)), ratio)
    state["qty"] = preview["new_qty"]
    state["avg_price"] = preview["new_avg"]
    state["last_updated"] = datetime.datetime.now().astimezone().isoformat()
    entry = {
        "date": state["last_updated"][:10], "ratio": ratio,
        "old_qty": preview["old_qty"], "old_avg": preview["old_avg"],
        "new_qty": preview["new_qty"], "new_avg": preview["new_avg"],
        "note": note or (f"{ratio:g}:1" if ratio >= 1 else f"1:{round(1/ratio):g}"),
    }
    state.setdefault("split_log", []).append(entry)
    return state


def format_preview(symbol: str, preview: dict) -> str:
    r = preview["ratio"]
    label = f"{r:g}:1 액면분할" if r >= 1 else f"1:{round(1/r):g} 역분할"
    return (
        f"📐 [{symbol}] {label} 미리보기\n\n"
        f"수량: {preview['old_qty']}주 → {preview['new_qty']}주\n"
        f"평단: ${preview['old_avg']:.4f} → ${preview['new_avg']:.4f}\n"
        f"T값·예수금: 변경 없음"
    )
