"""간이 백테스트: '점수가 기준 이상인 날 종가 신호 → 다음날 단타' 를 과거에 적용했으면?

규칙 (일봉만으로 하는 보수적 가정)
- 다음날 시가 매수
- 다음날 고가가 목표가(시가 + 0.5*ATR) 도달 → 목표가 매도 (익절)
- 다음날 저가가 손절가(시가 - 0.5*ATR) 도달 → 손절가 매도
- 둘 다 닿았으면 순서를 알 수 없으므로 손절로 처리 (보수적)
- 둘 다 아니면 종가 매도
- 왕복 거래비용 0.25% 차감 (수수료+거래세 근사)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COST = 0.25  # %


def next_day_trades(d: pd.DataFrame, score: pd.Series, threshold: float,
                    tp_atr: float = 0.5, sl_atr: float = 0.5) -> pd.DataFrame:
    nxt = d[["Open", "High", "Low", "Close"]].shift(-1)
    sel = (score >= threshold) & nxt.Open.notna() & d.ATR.notna()
    if not sel.any():
        return pd.DataFrame(columns=["ret", "result"])
    o, h, l, c = (nxt.loc[sel, k] for k in ("Open", "High", "Low", "Close"))
    atr = d.ATR[sel]
    tp, sl = o + tp_atr * atr, o - sl_atr * atr
    hit_tp, hit_sl = h >= tp, l <= sl
    exit_px = np.where(hit_sl, sl, np.where(hit_tp, tp, c))
    ret = (exit_px / o - 1) * 100 - COST
    result = np.where(hit_sl, "손절", np.where(hit_tp, "익절", "종가청산"))
    return pd.DataFrame({"ret": ret, "result": result}, index=o.index)


def summarize(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"거래수": 0, "승률%": None, "평균수익%": None, "누적수익%": None}
    r = trades.ret
    return {
        "거래수": n,
        "승률%": float(round((r > 0).mean() * 100, 1)),
        "평균수익%": float(round(r.mean(), 2)),
        "누적수익%": float(round(((1 + r / 100).prod() - 1) * 100, 1)),
    }
