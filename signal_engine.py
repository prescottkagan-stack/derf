import pandas as pd
import numpy as np

def calc_atr(df: pd.DataFrame, period=14) -> float:
    if df is None or len(df) < period + 1:
        return 0.0
    high  = df["high"]
    low   = df["low"]
    close = df["close"]
    prev  = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low  - prev).abs()
    ], axis=1).max(axis=1)
    result = tr.rolling(period).mean().iloc[-1]
    return round(float(result), 2) if pd.notna(result) else 0.0

def calc_vwap_bands(df: pd.DataFrame):
    if df is None or len(df) < 20:
        return 0.0, 0.0
    tp   = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    dev  = (tp - vwap).rolling(20).std()
    v = vwap.iloc[-1]
    d = dev.iloc[-1]
    return (
        round(float(v), 2) if pd.notna(v) else 0.0,
        round(float(d), 2) if pd.notna(d) else 0.0
    )

def calc_delta(df: pd.DataFrame) -> float:
    if df is None or len(df) < 6:
        return 0.0
    df = df.copy()
    df["delta"] = np.where(df["close"] >= df["open"], df["volume"], -df["volume"])
    return round(float(df["delta"].iloc[-6:].sum()), 0)

def calc_ivr(vix_current: float, vix_52w_high=36.0, vix_52w_low=11.0) -> int:
    if vix_52w_high == vix_52w_low or vix_current == 0.0:
        return 50
    ivr = (vix_current - vix_52w_low) / (vix_52w_high - vix_52w_low) * 100
    return int(min(max(ivr, 0), 100))

def calc_rvol(df: pd.DataFrame, lookback=10) -> float:
    if df is None or len(df) < lookback + 1:
        return 1.0
    recent = df["volume"].iloc[-1]
    avg    = df["volume"].iloc[-lookback - 1:-1].mean()
    return round(float(recent / avg), 2) if avg > 0 else 1.0

def classify_regime(df: pd.DataFrame) -> tuple:
    if df is None or len(df) < 20:
        return "Insufficient data", "Not enough bars to classify regime.", "#888780"
    close = df["close"]
    sma20 = close.rolling(20).mean().iloc[-1]
    sma5  = close.rolling(5).mean().iloc[-1]
    std20 = close.rolling(20).std().iloc[-1]
    last  = close.iloc[-1]
    z     = (last - sma20) / std20 if std20 > 0 else 0

    if abs(z) < 0.6:
        return "Mean-reverting", "Fade extremes at key levels. VWAP reversion trades preferred. Avoid breakout chasing.", "#7F77DD"
    elif sma5 > sma20:
        return "Trending bull", "Favor longs at pullbacks. Avoid counter-trend shorts unless at major resistance.", "#1D9E75"
    else:
        return "Trending bear", "Favor shorts at rallies. Wait for VWAP rejections to confirm entries.", "#D85A30"

def get_signals(df: pd.DataFrame, vol_mult: float) -> list:
    if df is None or len(df) < 20:
        return [{"dir": "F", "name": "No data", "detail": "Insufficient bars to generate signals.", "conf": 0, "src": "–"}]

    close     = df["close"].iloc[-1]
    prev      = df["close"].iloc[-2]
    vwap, sig = calc_vwap_bands(df)
    atr       = calc_atr(df)
    delta     = calc_delta(df)
    signals   = []

    if vwap == 0.0:
        return [{"dir": "F", "name": "No data", "detail": "VWAP could not be calculated.", "conf": 0, "src": "–"}]

    # 1. VWAP reclaim
    if prev < vwap <= close:
        conf = min(99, int(80 * vol_mult))
        signals.append({"dir": "L", "name": "VWAP reclaim",
                        "detail": f"Price reclaimed VWAP {vwap:.2f} — momentum shift",
                        "conf": conf, "src": "VWAP"})

    # 2. VWAP breakdown
    if prev > vwap >= close:
        conf = min(99, int(78 * vol_mult))
        signals.append({"dir": "S", "name": "VWAP breakdown",
                        "detail": f"Price lost VWAP {vwap:.2f} — bearish flip",
                        "conf": conf, "src": "VWAP"})

    # 3. Extended above +1σ
    if sig > 0 and close > vwap + sig:
        ext = round((close - (vwap + sig)) / atr, 1) if atr > 0 else 0
        conf = min(99, int(62 * (2.0 - min(vol_mult, 1.8))))
        signals.append({"dir": "S", "name": "VWAP +1σ fade",
                        "detail": f"Price {ext} ATR above upper band — overextended",
                        "conf": conf, "src": "VWAP+σ"})

    # 4. Extended below -1σ
    if sig > 0 and close < vwap - sig:
        ext = round(((vwap - sig) - close) / atr, 1) if atr > 0 else 0
        conf = min(99, int(60 * (2.0 - min(vol_mult, 1.8))))
        signals.append({"dir": "L", "name": "VWAP -1σ bounce",
                        "detail": f"Price {ext} ATR below lower band — reversion setup",
                        "conf": conf, "src": "VWAP+σ"})

    # 5. Bearish delta divergence
    if len(df) >= 6:
        price_up = close > df["close"].iloc[-6]
        if price_up and delta < 0:
            signals.append({"dir": "F", "name": "Bearish delta divergence",
                            "detail": "Price rising but selling delta dominates — await confirmation",
                            "conf": 55, "src": "Delta"})

        # 6. Bullish delta divergence
        price_dn = close < df["close"].iloc[-6]
        if price_dn and delta > 0:
            signals.append({"dir": "F", "name": "Bullish delta divergence",
                            "detail": "Price falling but buying delta dominates — possible reversal",
                            "conf": 55, "src": "Delta"})

    # 7. Momentum continuation long
    if len(df) >= 5:
        bars_up = int((df["close"].diff().iloc[-4:] > 0).sum())
        if bars_up == 4 and close > vwap and vol_mult >= 1.0:
            conf = min(99, int(70 * vol_mult))
            signals.append({"dir": "L", "name": "Momentum continuation",
                            "detail": "4 consecutive up-bars above VWAP in high-vol session",
                            "conf": conf, "src": "Momentum"})

        bars_dn = int((df["close"].diff().iloc[-4:] < 0).sum())
        if bars_dn == 4 and close < vwap and vol_mult >= 1.0:
            conf = min(99, int(70 * vol_mult))
            signals.append({"dir": "S", "name": "Momentum continuation",
                            "detail": "4 consecutive down-bars below VWAP in high-vol session",
                            "conf": conf, "src": "Momentum"})

    if not signals:
        signals.append({"dir": "F", "name": "No edge detected",
                        "detail": "Price in equilibrium — stand aside and wait for a setup",
                        "conf": 40, "src": "–"})

    return signals

def get_key_levels(df: pd.DataFrame) -> list:
    if df is None or len(df) < 20:
        return []
    close     = df["close"].iloc[-1]
    vwap, sig = calc_vwap_bands(df)
    atr       = calc_atr(df)

    prev_day = df.iloc[:-78] if len(df) > 78 else df
    pdh = round(float(prev_day["high"].max()), 2)
    pdl = round(float(prev_day["low"].min()), 2)

    levels = [
        {"price": round(vwap + 2 * sig, 2), "tag": "R",   "label": "VWAP +2σ"},
        {"price": round(vwap + sig,     2), "tag": "R",   "label": "VWAP +1σ"},
        {"price": pdh,                       "tag": "R",   "label": "Prev day high"},
        {"price": round(float(close),   2), "tag": "P",   "label": "Current price"},
        {"price": round(vwap,           2), "tag": "POC", "label": "VWAP"},
        {"price": pdl,                       "tag": "S",   "label": "Prev day low"},
        {"price": round(vwap - sig,     2), "tag": "S",   "label": "VWAP -1σ"},
        {"price": round(vwap - 2 * sig, 2), "tag": "S",   "label": "VWAP -2σ"},
    ]
    levels.sort(key=lambda x: x["price"], reverse=True)
    return levels
