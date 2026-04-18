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
    vwap, sigma = calc_vwap_bands(df)
    rvol     = calc_rvol(df)
    ivr      = calc_ivr(vix)
    regime, regime_tip, regime_color = classify_regime(df)
    signals  = get_signals(df, session["vol_mult"])
    levels   = get_key_levels(df)

    # ── Top metrics ───────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Last price",      f"{price:,.2f}",  f"{chg:+.2f} ({chg_pct:+.2f}%)")
    m2.metric("Session-adj ATR", f"{adj_atr} pts", f"raw {atr} × {session['vol_mult']}")
    m3.metric("VIX",             f"{vix}",          None)
    m4.metric("IV rank",         f"{ivr}%",         "elevated" if ivr > 60 else "normal")
    m5.metric("Rel volume",      f"{rvol}×",        "above avg" if rvol > 1.1 else "normal")

    st.divider()

    # ── Alerts ────────────────────────────────────────────────
    alerts = []
    if ivr > 60:
        alerts.append(("⚠️", "rgba(216,90,48,0.15)", "#F0997B", "IV rank elevated — reduce position size"))
    if rvol > 1.2:
        alerts.append(("⚠️", "rgba(216,90,48,0.15)", "#F0997B", f"Relative volume {rvol}× — widen stops"))
    if session["vol_mult"] >= 1.2:
        alerts.append(("ℹ️", "rgba(56,138,221,0.15)", "#85B7EB",
                        f"{session['label']} is a high-vol session — signals carry more weight"))
    if session["vol_mult"] <= 0.5:
        alerts.append(("✅", "rgba(99,153,34,0.15)", "#97C459",
                        "Low-vol session — reduce targets, avoid overtrading"))

    if alerts:
        cols = st.columns(len(alerts))
        for col, (icon, bg, fg, msg) in zip(cols, alerts):
            col.markdown(
                f'<div style="background:{bg};color:{fg};padding:8px 12px;'
                f'border-radius:8px;font-size:12px;border:1px solid {fg}44;">'
                f'{icon} {msg}</div>',
                unsafe_allow_html=True
            )
        st.markdown("")

    # ── Signals + Levels ──────────────────────────────────────
    col_sig, col_lvl = st.columns([1, 1])

    with col_sig:
        st.markdown("#### Signals")
        for s in signals:
            css   = "sig-long"  if s["dir"] == "L" else "sig-short" if s["dir"] == "S" else "sig-flat"
            arrow = "▲ Long"    if s["dir"] == "L" else "▼ Short"   if s["dir"] == "S" else "– Flat"
            conf_color = "#5DCAA5" if s["conf"] >= 70 else "#FAC775" if s["conf"] >= 55 else "#F0997B"
            st.markdown(
                f'<div class="sig-card {css}">'
                f'<div class="sig-name">{arrow} &nbsp; {s["name"]}'
                f'&nbsp;<span style="font-size:12px;color:{conf_color};font-weight:700;">{s["conf"]}%</span>'
                f'&nbsp;<span style="font-size:11px;opacity:0.5;">[{s["src"]}]</span></div>'
                f'<div class="sig-detail">{s["detail"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.progress(s["conf"] / 100)

    with col_lvl:
        st.markdown("#### Key levels")
        tag_css = {"R": "lvl-r", "S": "lvl-s", "POC": "lvl-poc", "P": "lvl-p"}
        rows = ""
        for lv in levels:
            css = tag_css.get(lv["tag"], "")
            rows += (
                f'<tr>'
                f'<td style="padding:6px 10px;"><span class="{css}">{lv["tag"]}</span></td>'
                f'<td style="padding:6px 10px;font-variant-numeric:tabular-nums;'
                f'font-weight:700;font-size:14px;">{lv["price"]}</td>'
                f'<td style="padding:6px 10px;font-size:12px;opacity:0.65;">{lv["label"]}</td>'
                f'</tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>'
            f'<th style="text-align:left;font-size:11px;opacity:0.5;padding:4px 10px;'
            f'font-weight:600;">Tag</th>'
            f'<th style="text-align:left;font-size:11px;opacity:0.5;padding:4px 10px;'
            f'font-weight:600;">Price</th>'
            f'<th style="text-align:left;font-size:11px;opacity:0.5;padding:4px 10px;'
            f'font-weight:600;">Level</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>',
            unsafe_allow_html=True
        )

    st.divider()

    # ── Chart + Regime ────────────────────────────────────────
    col_chart, col_regime = st.columns([3, 1])

    with col_chart:
        st.markdown("#### Price — last 78 bars")
        plot_df = df.iloc[-78:].copy()

        tp        = (plot_df["high"] + plot_df["low"] + plot_df["close"]) / 3
        vwap_line = (tp * plot_df["volume"]).cumsum() / plot_df["volume"].cumsum()
        dev_line  = (tp - vwap_line).rolling(20).std()

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df["open"],
            high=plot_df["high"],
            low=plot_df["low"],
            close=plot_df["close"],
            increasing_line_color="#1D9E75",
            decreasing_line_color="#D85A30",
            name=symbol,
        ))
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=vwap_line,
            line=dict(color="#AFA9EC", width=1.5),
            name="VWAP"
        ))
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=vwap_line + dev_line,
            line=dict(color="#7F77DD", width=1, dash="dot"),
            name="VWAP +1σ"
        ))
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=vwap_line - dev_line,
            line=dict(color="#7F77DD", width=1, dash="dot"),
            name="VWAP -1σ"
        ))
        fig.update_layout(
            height=380,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis_rangeslider_visible=False,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="left", x=0,
                font=dict(size=11)
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_regime:
        st.markdown("#### Market regime")
        st.markdown(
            f'<div style="background:{regime_color}22;border:1px solid {regime_color}66;'
            f'border-radius:10px;padding:14px 16px;margin-bottom:14px;">'
            f'<div style="font-size:17px;font-weight:700;color:{regime_color};">{regime}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div style="font-size:13px;opacity:0.75;line-height:1.7;">{regime_tip}</div>',
            unsafe_allow_html=True
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Session vol rank")
        sessions_all = [
            ("Asia",      0.55, "asia"),
            ("London",    0.85, "london"),
            ("NY AM",     1.35, "ny_am"),
            ("Lunch",     0.60, "ny_lunch"),
            ("NY PM",     1.10, "ny_pm"),
            ("After-hrs", 0.40, "afterhours"),
        ]
        for name, vm, sid in sessions_all:
            is_current = sid == session["id"]
            pct     = int(vm / 1.35 * 100)
            color   = session["color"] if is_current else "rgba(255,255,255,0.15)"
            weight  = "700" if is_current else "400"
            opacity = "1" if is_current else "0.5"
            st.markdown(
                f'<div style="margin-bottom:7px;opacity:{opacity};">'
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:12px;font-weight:{weight};margin-bottom:3px;">'
                f'<span>{name}</span><span>{vm}×</span></div>'
                f'<div style="height:5px;background:rgba(255,255,255,0.1);border-radius:3px;">'
                f'<div style="height:5px;width:{pct}%;background:{color};border-radius:3px;">'
                f'</div></div></div>',
                unsafe_allow_html=True
            )

    # ── Heatmap ───────────────────────────────────────────────
    st.divider()
    st.markdown("#### Intraday edge heatmap — signal type × session")

    heat_data = {
        "Signal":    ["Momentum", "Mean revert", "Gap fill", "VWAP fade", "OB bounce", "Breakout"],
        "Asia":      [20, 30, 10, 25, 35, 15],
        "London":    [55, 40, 65, 45, 50, 48],
        "NY AM":     [80, 25, 82, 55, 60, 78],
        "Lunch":     [35, 70, 30, 75, 55, 20],
        "NY PM":     [60, 50, 20, 65, 72, 55],
        "After-hrs": [15, 60, 10, 20, 40, 10],
    }
    heat_df = pd.DataFrame(heat_data).set_index("Signal")

    def color_heat(val):
        if val >= 75:
            return "background-color:#27500A;color:#C0DD97"
        if val >= 60:
            return "background-color:#085041;color:#9FE1CB"
        if val >= 45:
            return "background-color:#412402;color:#FAC775"
        if val >= 30:
            return "background-color:#4A1B0C;color:#F5C4B3"
        return "background-color:#2C2C2A;color:#888780"

    st.dataframe(
        heat_df.style.map(color_heat).format("{}%"),
        use_container_width=True,
        height=252
    )


with tab_es:
    render_instrument("ES")

with tab_nq:
    render_instrument("NQ")
