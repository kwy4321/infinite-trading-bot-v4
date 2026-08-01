"""Glassmorphism + compact dashboard CSS for Streamlit."""

from __future__ import annotations

import html

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.stApp {
  background:
    radial-gradient(ellipse 70% 50% at 8% 0%, rgba(99,102,241,0.20) 0%, transparent 50%),
    radial-gradient(ellipse 60% 45% at 92% 8%, rgba(236,72,153,0.12) 0%, transparent 48%),
    radial-gradient(ellipse 50% 35% at 50% 100%, rgba(56,189,248,0.08) 0%, transparent 52%),
    linear-gradient(165deg, #0a0e18 0%, #0f172a 50%, #0b1020 100%);
  background-attachment: fixed;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container {
  padding: 0.35rem 0.55rem 1rem !important;
  max-width: 100% !important;
}
[data-testid="stVerticalBlock"] > div { gap: 0.35rem !important; }
[data-testid="stHorizontalBlock"] { gap: 0.35rem !important; align-items: stretch; }

/* ── glass primitives ── */
.glass {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.10);
  box-shadow: 0 4px 24px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.06);
}

/* ── header ── */
.hdr {
  background: rgba(255,255,255,0.07);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  border: 1px solid rgba(255,255,255,0.11);
  border-radius: 12px;
  padding: 0.45rem 0.65rem;
  margin-bottom: 0.35rem;
  box-shadow: 0 6px 28px rgba(0,0,0,0.2);
}
.hdr-row { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.hdr .title { font-size: 0.95rem; font-weight: 800; color: #f1f5f9; letter-spacing: -0.02em; }
.hdr .meta { font-size: 0.62rem; color: #64748b; margin-top: 0.1rem; }
.badges { display: flex; flex-wrap: wrap; gap: 0.25rem; align-items: center; }
.badge {
  font-size: 0.58rem; font-weight: 700; padding: 0.12rem 0.42rem;
  border-radius: 999px; letter-spacing: 0.03em;
}
.b-live { background: rgba(34,211,165,.16); color: #34d399; border: 1px solid rgba(34,211,165,.22); }
.b-dry  { background: rgba(251,191,36,.16); color: #fbbf24; border: 1px solid rgba(251,191,36,.22); }
.b-run  { background: rgba(56,189,248,.16); color: #38bdf8; border: 1px solid rgba(56,189,248,.22); }
.b-stop { background: rgba(248,113,113,.16); color: #f87171; border: 1px solid rgba(248,113,113,.22); }

/* ── KPI strip (single row) ── */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 11px;
  overflow: hidden;
  margin-bottom: 0.35rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.16);
}
.kpi-item {
  padding: 0.4rem 0.45rem;
  border-right: 1px solid rgba(255,255,255,0.06);
  min-width: 0;
}
.kpi-item:last-child { border-right: none; }
.kpi-item .lbl { font-size: 0.58rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
.kpi-item .val { font-size: 0.92rem; font-weight: 750; color: #f8fafc; margin-top: 0.05rem; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-item .sub { font-size: 0.58rem; color: #475569; margin-top: 0.05rem; }

@media (max-width: 640px) {
  .kpi-strip { grid-template-columns: repeat(2, 1fr); }
  .kpi-item:nth-child(2) { border-right: none; }
  .kpi-item:nth-child(1), .kpi-item:nth-child(2) { border-bottom: 1px solid rgba(255,255,255,0.06); }
}

/* ── symbol table (한눈에) ── */
.sym-wrap {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 11px;
  overflow: hidden;
  margin-bottom: 0.35rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.14);
}
.sym-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
.sym-table thead th {
  padding: 0.28rem 0.4rem;
  font-size: 0.58rem; font-weight: 700; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.04em;
  background: rgba(255,255,255,0.04);
  border-bottom: 1px solid rgba(255,255,255,0.08);
  white-space: nowrap;
}
.sym-table tbody td {
  padding: 0.32rem 0.4rem;
  border-top: 1px solid rgba(255,255,255,0.05);
  color: #cbd5e1; vertical-align: middle;
}
.sym-table tbody tr:hover td { background: rgba(129,140,248,0.08); }
.sym-table .sym-n { font-weight: 800; color: #f1f5f9; font-size: 0.78rem; }
.sym-table .sym-s { font-size: 0.58rem; color: #64748b; display: block; margin-top: 0.02rem; }
.sym-table .pnl { font-weight: 700; white-space: nowrap; }
.t-bar { height: 4px; background: rgba(148,163,184,.12); border-radius: 99px; overflow: hidden; min-width: 48px; }
.t-bar > i { display: block; height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); border-radius: 99px; }

/* ── compact detail grid ── */
.kv {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.3rem;
  margin: 0.25rem 0 0.35rem;
}
.kv .c {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 8px;
  padding: 0.32rem 0.4rem;
}
.kv .c .k { font-size: 0.58rem; color: #64748b; font-weight: 600; }
.kv .c .v { font-size: 0.76rem; font-weight: 700; color: #e2e8f0; margin-top: 0.04rem; }
@media (max-width: 640px) { .kv { grid-template-columns: repeat(2, 1fr); } }

.detail-strip {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; margin-bottom: 0.25rem;
}
.mini-box {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 9px; padding: 0.35rem 0.45rem;
}
.mini-box .lbl { font-size: 0.58rem; color: #64748b; text-transform: uppercase; }
.mini-box .val { font-size: 0.88rem; font-weight: 750; color: #f8fafc; line-height: 1.15; }

.sec {
  font-size: 0.72rem; font-weight: 700; color: #94a3b8;
  margin: 0.35rem 0 0.2rem; letter-spacing: 0.04em; text-transform: uppercase;
}
.empty {
  text-align: center; color: #64748b; font-size: 0.75rem;
  padding: 0.75rem;
  border: 1px dashed rgba(255,255,255,0.10);
  border-radius: 10px;
  background: rgba(255,255,255,0.03);
  backdrop-filter: blur(8px);
}

.up { color: #34d399 !important; }
.down { color: #f87171 !important; }
.flat { color: #94a3b8 !important; }

.glass-login {
  max-width: 340px; margin: 2rem auto;
  background: rgba(255,255,255,0.07);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 16px; padding: 1.1rem;
}

/* ── Streamlit widgets → glass ── */
.stButton > button, .stLinkButton > a {
  min-height: 32px !important; height: 32px !important;
  padding: 0 0.55rem !important;
  font-size: 0.72rem !important; font-weight: 650 !important;
  border-radius: 8px !important;
  background: rgba(129,140,248,0.18) !important;
  border: 1px solid rgba(129,140,248,0.28) !important;
  color: #e0e7ff !important;
  backdrop-filter: blur(10px);
}
.stTabs [data-baseweb="tab-list"] {
  gap: 0.25rem;
  background: rgba(255,255,255,0.04);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  padding: 0.2rem 0.25rem;
}
.stTabs [data-baseweb="tab"] {
  min-height: 30px !important; height: 30px !important;
  font-size: 0.72rem !important; font-weight: 650 !important;
  padding: 0 0.55rem !important;
  border-radius: 7px !important;
  color: #94a3b8 !important;
  background: transparent !important;
}
.stTabs [aria-selected="true"] {
  background: rgba(129,140,248,0.22) !important;
  color: #e0e7ff !important;
  border: 1px solid rgba(129,140,248,0.25) !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 0.35rem !important; }

div[data-testid="stDataFrame"] {
  font-size: 0.72rem !important;
  background: rgba(255,255,255,0.04) !important;
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.08) !important;
  border-radius: 10px !important;
  overflow: hidden;
}
div[data-testid="stDataFrame"] div[data-testid="stTable"] {
  font-size: 0.72rem !important;
}

.stRadio > div {
  background: rgba(255,255,255,0.04);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 9px;
  padding: 0.15rem 0.25rem;
  gap: 0.2rem !important;
}
.stRadio label { font-size: 0.72rem !important; min-height: 28px !important; }

div[data-baseweb="select"], div[data-baseweb="input"] {
  font-size: 0.72rem !important;
}
.stSelectbox > div > div, .stMultiSelect > div > div {
  min-height: 32px !important;
  background: rgba(255,255,255,0.05) !important;
  border-color: rgba(255,255,255,0.10) !important;
  border-radius: 8px !important;
  backdrop-filter: blur(10px);
}

.stCaption { font-size: 0.62rem !important; color: #475569 !important; margin-top: -0.15rem !important; }

.stTextInput input {
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.12) !important;
  border-radius: 8px !important;
  color: #e2e8f0 !important;
  font-size: 0.82rem !important;
}
.stForm {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 0.75rem;
  backdrop-filter: blur(16px);
}
</style>
"""


def inject_dashboard_theme() -> None:
    import streamlit as st
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)


def glass_login_box(title: str, subtitle: str) -> str:
    return (
        f'<div class="glass-login hdr">'
        f'<div class="title">{html.escape(title)}</div>'
        f'<div class="meta">{html.escape(subtitle)}</div>'
        f"</div>"
    )
