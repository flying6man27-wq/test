"""간이 백테스트: 점수 기준 이상인 날 → 다음날 '시가 매수 → 종가 매도'.

- 다음날 저가가 (시가 - stop_atr × ATR) 이하이면 그 가격에 손절 (일봉만 쓰므로 장중 순서는 알 수 없음)
- 상한가 마감 종목은 제외 (실제로 살 수 없음)
- 왕복 거래비용 0.25% 차감 (수수료 + 거래세 근사)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COST = 0.25  # %


def next_day_trades(d: pd.DataFrame, score: pd.Series, threshold: float,
                    stop_atr: float | None = 1.0) -> pd.DataFrame:
    nxt = d[["Open", "Low", "Close"]].shift(-1)
    sel = (score >= threshold) & nxt.Open.notna() & d.ATR.notna() & (d.CHG_PCT < 29)
    if not sel.any():
        return pd.DataFrame(columns=["ret", "result"])
    o, l, c = nxt.Open[sel], nxt.Low[sel], nxt.Close[sel]
    if stop_atr:
        sl = o - stop_atr * d.ATR[sel]
        hit = l <= sl
        exit_px = np.where(hit, sl, c)
    else:
        hit = pd.Series(False, index=o.index)
        exit_px = c.values
    ret = (exit_px / o - 1) * 100 - COST
    return pd.DataFrame({"ret": ret, "result": np.where(hit, "손절", "종가청산")}, index=o.index)


def summarize(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"거래수": 0, "승률%": None, "평균수익%": None, "손절비율%": None}
    r = trades.ret
    return {
        "거래수": n,
        "승률%": float(round((r > 0).mean() * 100, 1)),
        "평균수익%": float(round(r.mean(), 2)),
        "손절비율%": float(round((trades.result == "손절").mean() * 100, 1)),
    }
