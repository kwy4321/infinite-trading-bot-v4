"""Glassmorphism + mobile-first CSS for Streamlit dashboard."""

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
    radial-gradient(ellipse 80% 60% at 10% 0%, rgba(99,102,241,0.22) 0%, transparent 55%),
    radial-gradient(ellipse 70% 50% at 90% 10%, rgba(236,72,153,0.14) 0%, transparent 50%),
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(56,189,248,0.10) 0%, transparent 55%),
    linear-gradient(160deg, #0b0f1a 0%, #111827 45%, #0f172a 100%);
  background-attachment: fixed;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container {
  padding: 0.55rem 0.7rem 2.5rem !important;
  max-width: 100% !important;
}
.stButton > button, .stLinkButton > a {
  min-height: 44px; font-size: 0.95rem; font-weight: 600;
  border-radius: 12px;
  background: rgba(129,140,248,0.22) !important;
  border: 1px solid rgba(129,140,248,0.35) !important;
  color: #e0e7ff !important;
}
.stTabs [data-baseweb="tab"] {
  min-height: 44px; font-size: 0.88rem; font-weight: 650; padding: 0 0.65rem;
}
div[data-testid="stHorizontalBlock"] { gap: 0.45rem; }
div[data-testid="stDataFrame"] {
  font-size: 0.82rem;
  background: rgba(255,255,255,0.04);
  backdrop-filter: blur(12px);
  border-radius: 12px;
}

.hdr {
  background: rgba(255,255,255,0.07);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 16px;
  padding: 0.85rem 0.95rem; margin-bottom: 0.75rem;
  box-shadow: 0 8px 32px rgba(0,0,0,0.22);
}
.hdr .title { font-size: 1.15rem; font-weight: 800; color: #f1f5f9; }
.hdr .meta { font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; }
.badges { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.55rem; }
.badge {
  font-size: 0.7rem; font-weight: 700; padding: 0.2rem 0.55rem;
  border-radius: 999px;
}
.b-live { background: rgba(34,211,165,.18); color: #34d399; border: 1px solid rgba(34,211,165,.25); }
.b-dry  { background: rgba(251,191,36,.18); color: #fbbf24; border: 1px solid rgba(251,191,36,.25); }
.b-run  { background: rgba(56,189,248,.18); color: #38bdf8; border: 1px solid rgba(56,189,248,.25); }
.b-stop { background: rgba(248,113,113,.18); color: #f87171; border: 1px solid rgba(248,113,113,.25); }

.box {
  background: rgba(255,255,255,0.07);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border: 1px solid rgba(255,255,255,0.11);
  border-radius: 14px;
  padding: 0.75rem 0.85rem; margin-bottom: 0.55rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
.box .lbl { font-size: 0.68rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }
.box .val { font-size: 1.35rem; font-weight: 750; color: #f8fafc; margin-top: 0.15rem; line-height: 1.2; }
.box .sub { font-size: 0.72rem; color: #64748b; margin-top: 0.2rem; }

.sym {
  background: rgba(255,255,255,0.06);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 16px;
  padding: 0.9rem 1rem; margin-bottom: 0.65rem;
  box-shadow: 0 4px 24px rgba(0,0,0,0.18);
}
.sym-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }
.sym-name { font-size: 1.2rem; font-weight: 800; color: #f8fafc; }
.sym-pnl { text-align: right; font-size: 1rem; font-weight: 700; }
.sym-meta { font-size: 0.75rem; color: #94a3b8; margin-top: 0.35rem; }
.sym-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0.55rem; margin-top: 0.7rem;
}
.sym-cell {
  background: rgba(148,163,184,.08);
  backdrop-filter: blur(8px);
  border-radius: 10px; padding: 0.5rem 0.6rem;
  border: 1px solid rgba(255,255,255,0.06);
}
.sym-cell .k { font-size: 0.65rem; color: #64748b; }
.sym-cell .v { font-size: 0.92rem; font-weight: 700; color: #e2e8f0; margin-top: 0.1rem; }

.bar { height: 6px; background: rgba(148,163,184,.15); border-radius: 99px; margin-top: 0.55rem; overflow: hidden; }
.bar > i { display: block; height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); border-radius: 99px; }

.up { color: #34d399 !important; }
.down { color: #f87171 !important; }
.flat { color: #94a3b8 !important; }

.sec { font-size: 0.95rem; font-weight: 700; color: #e2e8f0; margin: 1rem 0 0.5rem; }
.empty {
  text-align: center; color: #64748b; font-size: 0.88rem;
  padding: 1.5rem 0.75rem;
  border: 1px dashed rgba(255,255,255,0.12);
  border-radius: 14px;
  background: rgba(255,255,255,0.03);
}

.kv { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin-top: 0.65rem; }
.kv .c {
  background: rgba(148,163,184,.08);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px; padding: 0.55rem 0.65rem;
}
.kv .c .k { font-size: 0.65rem; color: #64748b; }
.kv .c .v { font-size: 0.88rem; font-weight: 700; color: #e2e8f0; margin-top: 0.08rem; }

.glass-login {
  max-width: 380px; margin: 3rem auto;
  background: rgba(255,255,255,0.07);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 20px; padding: 1.5rem;
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
