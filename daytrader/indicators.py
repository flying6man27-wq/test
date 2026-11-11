"""기술적 지표 계산."""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d.Close, d.High, d.Low, d.Volume

    for n in (5, 20, 60):
        d[f"MA{n}"] = c.rolling(n).mean()

    # RSI(14) - Wilder
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    # RSI(2) - 초단기 과매도 측정
    g2 = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    l2 = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    d["RSI2"] = 100 - 100 / (1 + g2 / l2.replace(0, np.nan))

    # MACD(12,26,9)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    d["MACD"] = ema12 - ema26
    d["MACD_SIG"] = d.MACD.ewm(span=9, adjust=False).mean()
    d["MACD_HIST"] = d.MACD - d.MACD_SIG

    # 볼린저밴드(20, 2)
    std = c.rolling(20).std()
    d["BB_UP"], d["BB_LO"] = d.MA20 + 2 * std, d.MA20 - 2 * std
    d["BB_WIDTH"] = (d.BB_UP - d.BB_LO) / d.MA20

    # 스토캐스틱 슬로우(14,3,3)
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    fast_k = 100 * (c - ll) / (hh - ll).replace(0, np.nan)
    d["STO_K"] = fast_k.rolling(3).mean()
    d["STO_D"] = d.STO_K.rolling(3).mean()

    # ATR(14)
    prev_c = c.shift()
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    d["ATR_PCT"] = d.ATR / c * 100

    # 거래량 / 거래대금
    d["VOL_MA20"] = v.rolling(20).mean()
    d["VOL_RATIO"] = v / d.VOL_MA20.shift()
    d["AMOUNT"] = c * v
    d["AMOUNT_MA20"] = d.AMOUNT.rolling(20).mean()

    d["HIGH20"] = h.rolling(20).max().shift()  # 전일까지 20일 최고가
    d["CHG_PCT"] = c.pct_change() * 100
    rng = (h - l).replace(0, np.nan)
    d["CLOSE_POS"] = (c - l) / rng                       # 1에 가까울수록 고가 마감
    d["UPPER_SHADOW"] = (h - np.maximum(c, d.Open)) / rng  # 윗꼬리 비율
    return d
