"""Streamlit dashboard — glassmorphism UI, mobile-first."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import App
from config.settings import SYMBOLS, get_settings
from dashboard.glass_theme import glass_login_box, inject_dashboard_theme
from reporting.dashboard_data import (
    collect_all_trades,
    collect_completed_cycles,
    collect_monthly_rows,
    collect_portfolio_snapshot,
    collect_symbol_status,
    prepare_ledger_for_export,
)

TRADE_MOBILE = ["date", "side", "qty", "price", "amount_usd", "note"]
TRADE_LABELS = {
    "date": "일자", "symbol": "종목", "side": "구분", "qty": "수량",
    "price": "단가", "amount_usd": "금액", "cycle_no": "회차", "note": "비고",
}
SIDE_KO = {"BUY": "매수", "SELL": "매도"}


@st.cache_resource
def get_app() -> App:
    return App.create()


def _auth(settings) -> bool:
    pwd = (settings.streamlit_password or "").strip()
    if not pwd or st.session_state.get("authed"):
        return True
    st.markdown(
        glass_login_box("♾️ 라오어 무한매수 4.0", "대시보드 접속을 위해 비밀번호를 입력하세요"),
        unsafe_allow_html=True,
    )
    with st.form("login"):
        p = st.text_input("비밀번호", type="password", placeholder="비밀번호")
        if st.form_submit_button("입장", use_container_width=True, type="primary"):
            if p == pwd:
                st.session_state["authed"] = True
                st.rerun()
            st.error("비밀번호 오류")
    return False


def _cls(v: float) -> str:
    return "up" if v > 0 else "down" if v < 0 else "flat"


def _usd(v: float, signed: bool = False) -> str:
    return f"${v:+,.2f}" if signed else f"${v:,.2f}"


def _header(snapshot: dict) -> None:
    live = not snapshot["dry_run"]
    paused = snapshot["paused"]
    when = str(snapshot.get("updated_at", ""))[:16].replace("T", " ")
    st.markdown(
        f"""
        <div class="hdr">
          <div class="title">♾️ 무한매수 4.0</div>
          <div class="meta">갱신 {when}</div>
          <div class="badges">
            <span class="badge {'b-live' if live else 'b-dry'}">{'LIVE' if live else 'DRY'}</span>
            <span class="badge {'b-stop' if paused else 'b-run'}">{'정지' if paused else '운영'}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _kpi_box(label: str, value: str, sub: str = "", tone: str = "") -> str:
    return f"""
    <div class="box">
      <div class="lbl">{label}</div>
      <div class="val {tone}">{value}</div>
      <div class="sub">{sub or '&nbsp;'}</div>
    </div>"""


def _kpis(snapshot: dict) -> None:
    acc = snapshot["account"]
    total = float(acc.get("total_usd", 0))
    unreal = float(acc.get("unreal_usd", 0))
    realized = float(snapshot.get("realized_usd", 0))
    cash = float(acc.get("cash_usd", 0))
    krw = float(acc.get("total_krw", 0))

    r1a, r1b = st.columns(2)
    with r1a:
        st.markdown(_kpi_box("총 자산", _usd(total), f"₩{krw:,.0f}" if krw else ""), unsafe_allow_html=True)
    with r1b:
        st.markdown(_kpi_box("평가 손익", _usd(unreal, True), "", _cls(unreal)), unsafe_allow_html=True)
    r2a, r2b = st.columns(2)
    with r2a:
        st.markdown(
            _kpi_box("실현 수익", _usd(realized, True), f"완료 {snapshot.get('completed_cycles', 0)}회", _cls(realized)),
            unsafe_allow_html=True,
        )
    with r2b:
        st.markdown(
            _kpi_box("진행 회차", str(snapshot.get("active_cycles", 0)), f"예수금 {_usd(cash)}" if cash else ""),
            unsafe_allow_html=True,
        )


def _symbol_block(row: dict) -> None:
    sym = row.get("symbol", "?")
    pnl_u = float(row.get("cycle_pnl_usd") or 0)
    pnl_p = float(row.get("cycle_pnl_pct") or 0)
    t_val = float(row.get("T") or 0)
    split = int(row.get("split_count") or 1)
    pct = min(100.0, t_val / split * 100 if split else 0)
    state = "거래중" if row.get("active") else "대기"

    st.markdown(
        f"""
        <div class="sym">
          <div class="sym-top">
            <div>
              <div class="sym-name">{sym}</div>
              <div class="sym-meta">{state} · {row.get('mode_label', '')} · {row.get('cycle_no', '—')}회차</div>
            </div>
            <div class="sym-pnl {_cls(pnl_u)}">{_usd(pnl_u, True)}<br><span style="font-size:0.78rem">{pnl_p:+.1f}%</span></div>
          </div>
          <div class="sym-row">
            <div class="sym-cell"><div class="k">수량</div><div class="v">{int(row.get('qty') or 0):,}</div></div>
            <div class="sym-cell"><div class="k">평단</div><div class="v">${float(row.get('avg_price') or 0):,.2f}</div></div>
            <div class="sym-cell"><div class="k">현재가</div><div class="v">${float(row.get('current_price') or 0):,.2f}</div></div>
            <div class="sym-cell"><div class="k">평가</div><div class="v">${float(row.get('eval_usd') or 0):,.0f}</div></div>
          </div>
          <div class="sym-meta" style="margin-top:0.55rem">T {t_val:g} / {split} · {pct:.0f}%</div>
          <div class="bar"><i style="width:{pct:.0f}%"></i></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _trades_df(trades: list[dict], symbol: str | None = None) -> pd.DataFrame:
    rows = trades if symbol is None else [t for t in trades if t.get("symbol") == symbol]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("datetime", ascending=False)
    df["side"] = df["side"].map(lambda s: SIDE_KO.get(str(s).upper(), s))
    cols = [c for c in TRADE_MOBILE if c in df.columns]
    return df[cols].rename(columns={k: TRADE_LABELS[k] for k in cols})


def _show_trades(df: pd.DataFrame, height: int = 360) -> None:
    if df.empty:
        st.markdown('<div class="empty">체결 내역 없음</div>', unsafe_allow_html=True)
        return
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            "일자": st.column_config.TextColumn(width="small"),
            "구분": st.column_config.TextColumn(width="small"),
            "수량": st.column_config.NumberColumn(format="%d"),
            "단가": st.column_config.NumberColumn(format="$%.2f"),
            "금액": st.column_config.NumberColumn(format="$%.0f"),
        },
    )


def _detail(app: App, symbol: str, trades: list[dict]) -> None:
    d = collect_symbol_status(app, symbol, fetch_live_price=True)
    pnl_u = float(d.get("cycle_pnl_usd") or 0)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(_kpi_box("T", f"{float(d.get('T', 0)):g}", f"분할 {d.get('split_count', '—')}"), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_box("손익", _usd(pnl_u, True), f"{float(d.get('cycle_pnl_pct') or 0):+.1f}%", _cls(pnl_u)), unsafe_allow_html=True)

    cells = [
        ("수량", f"{int(d.get('qty') or 0):,}"),
        ("평단", f"${float(d.get('avg_price') or 0):,.2f}"),
        ("현재가", f"${float(d.get('current_price') or 0):,.2f}"),
        ("평가", _usd(float(d.get("eval_usd", 0)))),
        ("원금", _usd(float(d.get("principal", 0)))),
        ("목표", f"{float(d.get('take_profit_pct', 0)):g}%"),
        ("역매수", "ON" if d.get("reverse_mode") else "OFF"),
        ("강제1회", "ON" if d.get("force_one") else "OFF"),
    ]
    html_cells = "".join(f'<div class="c"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in cells)
    st.markdown(f'<div class="kv">{html_cells}</div>', unsafe_allow_html=True)

    st.markdown('<div class="sec">최근 체결</div>', unsafe_allow_html=True)
    _show_trades(_trades_df(trades, symbol), height=280)


def main() -> None:
    settings = get_settings()
    st.set_page_config(
        page_title="무한매수 4.0",
        page_icon="♾️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_dashboard_theme()

    if not _auth(settings):
        st.stop()

    app = get_app()
    prepare_ledger_for_export(app)
    snapshot = collect_portfolio_snapshot(app, fetch_live_price=True)
    trades = collect_all_trades(app)
    symbols = snapshot.get("symbols") or []

    _header(snapshot)

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()
    with b2:
        if settings.google_sheets_link:
            st.link_button("📗 Sheets", settings.google_sheets_link, use_container_width=True)

    if settings.streamlit_link:
        st.caption(f"📱 {settings.streamlit_link}")

    _kpis(snapshot)

    st.markdown('<div class="sec">종목</div>', unsafe_allow_html=True)
    if symbols:
        for row in symbols:
            _symbol_block(row)
    else:
        st.markdown('<div class="empty">종목 없음</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["상세", "체결", "회차", "월별"])

    with tab1:
        names = [s.get("symbol") for s in symbols if s.get("symbol")] or list(SYMBOLS)
        pick = st.radio("종목", names, horizontal=True, label_visibility="collapsed")
        if pick:
            _detail(app, pick, trades)

    with tab2:
        syms = st.multiselect("종목", SYMBOLS, default=list(SYMBOLS), placeholder="종목")
        side = st.selectbox("구분", ["전체", "매수", "매도"], label_visibility="collapsed")
        df = pd.DataFrame(trades)
        if syms:
            df = df[df["symbol"].isin(syms)]
        if side != "전체":
            want = "BUY" if side == "매수" else "SELL"
            df = df[df["side"].str.upper() == want]
        df = df.sort_values("datetime", ascending=False) if not df.empty else df
        if df.empty:
            st.markdown('<div class="empty">체결 없음</div>', unsafe_allow_html=True)
        else:
            tmp = df.copy()
            tmp["side"] = tmp["side"].map(lambda s: SIDE_KO.get(str(s).upper(), s))
            cols = [c for c in TRADE_MOBILE if c in tmp.columns]
            show = tmp[cols].rename(columns={k: TRADE_LABELS[k] for k in cols})
            st.caption(f"총 {len(show)}건")
            _show_trades(show, height=420)

    with tab3:
        cycles = collect_completed_cycles(app)
        if cycles:
            cdf = pd.DataFrame(cycles)
            show_cols = {
                "symbol": "종목", "cycle_no": "회차", "ended_at": "종료",
                "profit_usd": "실현", "profit_pct": "수익률",
            }
            cols = [c for c in show_cols if c in cdf.columns]
            st.dataframe(
                cdf[cols].rename(columns={k: show_cols[k] for k in cols}),
                use_container_width=True,
                hide_index=True,
                height=400,
                column_config={
                    "실현": st.column_config.NumberColumn(format="$%.2f"),
                    "수익률": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
        else:
            st.markdown('<div class="empty">완료 회차 없음</div>', unsafe_allow_html=True)

    with tab4:
        year = st.selectbox("연도", list(range(datetime.date.today().year, 2019, -1)), label_visibility="collapsed")
        monthly = collect_monthly_rows(app, int(year))
        if monthly:
            mdf = pd.DataFrame([m for m in monthly if m.get("scope") == "전체"])
            if not mdf.empty:
                mdf = mdf.rename(columns={
                    "month": "월", "cycles": "회차",
                    "profit_usd": "실현", "profit_pct_on_buy": "수익률",
                })
                st.dataframe(
                    mdf[["월", "회차", "실현", "수익률"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "실현": st.column_config.NumberColumn(format="$%.0f"),
                        "수익률": st.column_config.NumberColumn(format="%.1f%%"),
                    },
                )
            else:
                st.markdown('<div class="empty">데이터 없음</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="empty">{year}년 기록 없음</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
