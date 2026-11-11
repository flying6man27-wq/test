"""전략 검증: 여러 종목의 과거 데이터를 합쳐서 '점수가 높을수록 다음날 실제로 올랐나?'를 확인.

전략(가중치)을 바꿀 때마다 반드시 돌려볼 것. 점수 구간이 높을수록 수익이 높아야
'의미 있는 점수'이고, 그렇지 않다면 그 점수로 추천하는 것은 근거가 없다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import backtest, data, strategy
from .indicators import add_indicators
from .scanner import universe

BUCKETS = [-1, 20, 40, 55, 70, 101]
LABELS = ["0-20", "20-40", "40-55", "55-70", "70+"]


def _one(code: str, threshold: float):
    try:
        d = add_indicators(data.ohlcv(code))
    except Exception:
        return None
    s = strategy.score_series(strategy.signal_frame(d))
    n = d.shift(-1)
    fwd = pd.DataFrame({
        "score": s,
        "종가→익일시가%": (n.Open / d.Close - 1) * 100,
        "익일시가→종가%": (n.Close / n.Open - 1) * 100,
        "종가→익일종가%": (n.Close / d.Close - 1) * 100,
    }).dropna().iloc[60:]  # 지표 안정화 구간 제외
    trades = backtest.next_day_trades(d.iloc[60:], s.iloc[60:], threshold)
    return fwd, trades


def run(market="ALL", limit=150, min_amount_eok=30, threshold=55, workers=8):
    codes = universe(market, limit, min_amount_eok).Code
    with ThreadPoolExecutor(workers) as ex:
        res = [r for r in ex.map(lambda c: _one(c, threshold), codes) if r]
    fwd = pd.concat([r[0] for r in res])
    trades = pd.concat([r[1] for r in res if len(r[1])])
    fwd["점수구간"] = pd.cut(fwd.score, BUCKETS, labels=LABELS)
    g = fwd.groupby("점수구간", observed=True)
    cols = ["종가→익일시가%", "익일시가→종가%", "종가→익일종가%"]
    table = pd.concat([g.size().rename("표본수"), g[cols].mean().round(2),
                       g["익일시가→종가%"].apply(lambda x: round((x > 0).mean() * 100, 1)).rename("시가→종가 승률%")],
                      axis=1)
    return len(res), table, backtest.summarize(trades)
