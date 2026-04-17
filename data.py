import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz

TICKERS = {"ES": "ES=F", "NQ": "NQ=F", "VIX": "^VIX"}

def get_bars(symbol: str, period="5d", interval="5m") -> pd.DataFrame:
    ticker = TICKERS.get(symbol, symbol)
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    df = df.dropna()
    return df

def get_quote(symbol: str) -> dict:
    ticker = TICKERS.get(symbol, symbol)
    t = yf.Ticker(ticker)
    info = t.fast_info
    return {
        "price": round(info.last_price, 2),
        "prev_close": round(info.previous_close, 2),
    }

def get_vix() -> float:
    t = yf.Ticker("^VIX")
    return round(t.fast_info.last_price, 2)

def get_current_session() -> dict:
    now = datetime.now(pytz.timezone("America/New_York"))
    h = now.hour
    sessions = [
        {"id": "asia",       "label": "Asia",        "start": 18, "end": 2,  "vol_mult": 0.55, "color": "#AFA9EC"},
        {"id": "london",     "label": "London open", "start": 3,  "end": 8,  "vol_mult": 0.85, "color": "#5DCAA5"},
        {"id": "ny_am",      "label": "NY AM",       "start": 9,  "end": 11, "vol_mult": 1.35, "color": "#F0997B"},
        {"id": "ny_lunch",   "label": "NY lunch",    "start": 11, "end": 13, "vol_mult": 0.60, "color": "#FAC775"},
        {"id": "ny_pm",      "label": "NY PM",       "start": 13, "end": 16, "vol_mult": 1.10, "color": "#85B7EB"},
        {"id": "afterhours", "label": "After-hours", "start": 16, "end": 18, "vol_mult": 0.40, "color": "#B4B2A9"},
    ]
    for s in sessions:
        if s["start"] > s["end"]:
            if h >= s["start"] or h < s["end"]:
                return {**s, "now": now}
        else:
            if s["start"] <= h < s["end"]:
                return {**s, "now": now}
    return {**sessions[-1], "now": now}
