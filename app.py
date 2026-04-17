import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import pytz
from datetime import datetime

from data import get_bars, get_quote, get_vix, get_current_session
from signal_engine import (
    calc_atr, calc_vwap_bands, calc_rvol, calc_ivr,
    classify_regime, get_signals, get_key_levels
)

st.set_page_config(
    page_title="ES · NQ Quant Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st_autorefresh(interval=60_000, key="auto_refresh")

st.markdown("""
<style>
  .block-container { padding-top: 1rem; padding-bottom: 1rem; }

  .sig-card {
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    border: 1px solid rgba(255,255,255,0.1);
  }
  .sig-long  {
    background: rgba(29, 158, 117, 0.15);
    border-left: 4px solid #1D9E75;
  }
  .sig-short {
    background: rgba(216, 90, 48, 0.15);
    border-left: 4px solid #D85A30;
  }
  .sig-flat  {
    background: rgba(136, 135, 128, 0.15);
    border-left: 4px solid #888780;
  }
  .sig-name   { font-weight: 700; font-size: 15px; color: inherit; }
  .sig-detail { font-size: 13px; opacity: 0.75; margin-top: 4px; color: inherit; }

  .lvl-r   { color: #F0997B; font-weight: 700; }
  .lvl-s   { color: #5DCAA5; font-weight: 700; }
  .lvl-poc { color: #FAC775; font-weight: 700; }
  .lvl-p   { color: #85B7EB; font-weight: 700; }

  table td, table th { color: inherit !important; }

  .session-badge {
    display: inline-block; padding: 3px 12px;
    border-radius: 20px; font-size: 13px; font-weight: 600;
  }
  div[data-testid="metric-container"] > label { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────
session = get_current_session()
et_now  = session["now"].strftime("%H:%M:%S ET")

col_title, col_session = st.columns([3, 1])
with col_title:
    st.markdown("## ES · NQ Quant Signal Dashboard")
with col_session:
    st.markdown(
        f'<div style="text-align:right;padding-top:8px;">'
        f'<span class="session-badge" style="background:{session["color"]}33;'
        f'color:{session["color"]};border:1px solid {session["color"]}66;">'
        f'{session["label"]}</span>'
        f'<br><small style="color:#888">{et_now} · vol ×{session["vol_mult"]}</small></div>',
        unsafe_allow_html=True
    )

tab_es, tab_nq = st.tabs(["📊  ES — S&P 500 Futures", "📊  NQ — Nasdaq Futures"])

def render_instrument(symbol: str):

    @st.cache_data(ttl=60, show_spinner=False)
    def load_data(sym):
        df    = get_bars(sym)
        quote = get_quote(sym)
        vix   = get_vix()
        return df, quote, vix

    with st.spinner(f"Loading {symbol} data…"):
        df, quote, vix = load_data(symbol)

    if df is None or len(df) < 20:
        st.warning(
            f"Not enough data for {symbol} — market may be closed or data unavailable. "
            f"Try again during market hours."
        )
        return

    price    = quote["price"]
    prev_cls = quote["prev_close"]
    chg      = round(price - prev_cls, 2) if price and prev_cls else 0.0
    chg_pct  = round(chg / prev_cls * 100, 2) if prev_cls else 0.0
    atr      = calc_atr(df)
    adj_atr  = round(atr * session["vol_mult"], 2)
    vwap, sigma          = calc_vwap_bands(df)
    rvol     = calc_rvol(df)
    ivr      = calc_ivr(vix)
    regime, regime_tip, regime_color = classify_regime(df)
    signals  = get_signals(df, session["vol_mult"])
    levels   = get_key_levels(df)

    # ── Top metrics ───────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Last price",      f"{price:,.2f}",  f"{chg:+.2f} ({chg_pct:+.2f}%)")
    m2.metric("Session-adj ATR"
