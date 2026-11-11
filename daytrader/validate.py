"""전략 검증: 여러 종목의 과거 데이터를 합쳐 '점수가 높을수록 다음날 실제로 수익이 났나?'를 확인.

- 다음날 '시가→종가' 수익을 점수 구간별로 비교한다.
- '초과%'는 같은 날 전체 종목 평균 대비 수익. 상승장·하락장 영향을 뺀 순수 신호 효과다.
- 기간을 앞(학습)·뒤(검증)로 나눠 양쪽에서 모두 성립하는지 본다.
전략(가중치)을 바꿀 때마다 반드시 돌려볼 것.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import backtest, data, strategy
from .indicators import add_indicators
from .scanner import universe

BUCKETS = [-1, 20, 40, 60, 75, 101]
LABELS = ["0-20", "20-40", "40-60", "60-75", "75+"]


def _one(code: str, strat, threshold: float, days: int):
    try:
        d = add_indicators(data.ohlcv(code, days))
    except Exception:
        return None
    if len(d) < 120:
        return None
    s = strat.score_series(strat.signal_frame(d))
    n = d.shift(-1)
    fwd = pd.DataFrame({"score": s, "id": (n.Close / n.Open - 1) * 100,
                        "limit_up": d.CHG_PCT >= 29}).iloc[60:].dropna()
    trades = backtest.next_day_trades(d.iloc[60:], s.iloc[60:], threshold, strategy.STOP_ATR)
    return fwd, trades


def _table(fwd: pd.DataFrame) -> pd.DataFrame:
    g = fwd.groupby(pd.cut(fwd.score, BUCKETS, labels=LABELS), observed=True)
    return pd.DataFrame({
        "표본수": g.size(),
        "시가→종가%": g.id.mean().round(2),
        "초과%": g.id_x.mean().round(2),
        "승률%": g.id.apply(lambda x: round((x > 0).mean() * 100, 1)),
    })


def run(market="ALL", limit=300, min_amount_eok=30, strat=None, threshold=None,
        workers=8, years=4, split=None):
    strat = strat or strategy.get()
    threshold = strat.default_threshold if threshold is None else threshold
    codes = universe(market, limit, min_amount_eok).Code
    days = int(365 * years)
    with ThreadPoolExecutor(workers) as ex:
        res = [r for r in ex.map(lambda c: _one(c, strat, threshold, days), codes) if r]
    fwd = pd.concat([r[0] for r in res])
    fwd = fwd[~fwd.limit_up]
    fwd["id_x"] = fwd.id - fwd.groupby(level=0).id.transform("mean")
    trades = pd.concat([r[1] for r in res if len(r[1])]) if any(len(r[1]) for r in res) \
        else pd.DataFrame(columns=["ret", "result"])

    dates = fwd.index.sort_values()
    split = pd.Timestamp(split) if split else dates[int(len(dates) * 0.6)]
    early, late = fwd[fwd.index < split], fwd[fwd.index >= split]
    t_early, t_late = trades[trades.index < split], trades[trades.index >= split]
    share = trades.groupby(level=0).size() / len(res) * 100
    trades = trades.assign(share=trades.index.map(share))
    band = pd.cut(trades.share, [0, 2, 5, 10, 100], labels=["~2%", "2-5%", "5-10%", "10%+"])
    by_share = trades.groupby(band, observed=True).ret.agg(
        거래수="size", 평균수익="mean", 승률=lambda r: (r > 0).mean() * 100).round(2)
    panic = trades[trades.share >= 10].groupby(level=0).ret.mean()
    panic_days = {"일수": len(panic), "일평균수익%": float(round(panic.mean(), 2)) if len(panic) else None,
                  "수익난날%": float(round((panic > 0).mean() * 100, 1)) if len(panic) else None,
                  "최악의날%": float(round(panic.min(), 2)) if len(panic) else None}
    yearly = trades.groupby(trades.index.year).ret.agg(
        거래수="size", 평균수익="mean", 승률=lambda r: (r > 0).mean() * 100).round(2)
    return {
        "n_stocks": len(res), "start": dates[0].date(), "end": dates[-1].date(), "split": split.date(),
        "threshold": threshold,
        "table_all": _table(fwd), "table_early": _table(early), "table_late": _table(late),
        "bt_all": backtest.summarize(trades), "bt_early": backtest.summarize(t_early),
        "bt_late": backtest.summarize(t_late), "yearly": yearly,
        "by_share": by_share, "panic_days": panic_days,
    }


def verdict(r: dict) -> tuple[bool, str]:
    """고득점 구간 초과수익이 앞·뒤 기간 모두 플러스이고, 백테스트 평균이 앞·뒤 모두 플러스여야 통과."""
    def top_excess(t):
        hi = t[t.index.isin(["60-75", "75+"])]
        return np.average(hi["초과%"], weights=hi["표본수"]) if hi["표본수"].sum() else np.nan
    e, l = top_excess(r["table_early"]), top_excess(r["table_late"])
    be, bl = r["bt_early"]["평균수익%"], r["bt_late"]["평균수익%"]
    ok = all(x is not None and x == x and x > 0 for x in (e, l, be, bl))
    msg = (f"고득점(60+) 초과수익: 앞 기간 {e:+.2f}%, 뒤 기간 {l:+.2f}% / "
           f"백테스트 평균(비용 차감): 앞 {be}%, 뒤 {bl}%")
    return ok, msg
