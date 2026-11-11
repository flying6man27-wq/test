"""종목 1개 분석."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import backtest, data, strategy
from .indicators import add_indicators

MIN_BARS = 80


@dataclass
class Result:
    code: str
    name: str
    date: str
    strategy: str
    close: float
    chg_pct: float
    score: float
    grade: str
    signals_on: list[str]
    warnings: list[str]
    plan: dict
    amount: float           # 당일 거래대금
    rsi: float
    vol_ratio: float
    atr_pct: float
    backtest: dict = field(default_factory=dict)

    def row(self) -> dict:
        return {
            "코드": self.code, "종목": self.name, "기준일": self.date,
            "종가": self.close, "등락%": round(self.chg_pct, 2),
            "점수": self.score, "등급": self.grade.split()[0],
            "RSI": round(self.rsi, 1), "거래량배수": round(self.vol_ratio, 2),
            "ATR%": round(self.atr_pct, 2),
            "거래대금(억)": round(self.amount / 1e8, 1),
            "손절폭": round(self.plan["손절폭"], 2),
            "과거승률%": self.backtest.get("승률%"), "과거평균%": self.backtest.get("평균수익%"),
            "과거거래수": self.backtest.get("거래수"),
            "주요신호": ", ".join(self.signals_on),
            "주의": ", ".join(self.warnings),
        }


def analyze_df(code: str, name: str, df: pd.DataFrame,
               strat: strategy.Strategy | None = None, threshold: float | None = None) -> Result:
    strat = strat or strategy.get()
    threshold = strat.default_threshold if threshold is None else threshold
    if len(df) < MIN_BARS:
        raise ValueError(f"데이터 부족 ({len(df)}일)")
    d = add_indicators(df)
    sig = strat.signal_frame(d)
    score = strat.score_series(sig)
    last, s_last = d.iloc[-1], sig.iloc[-1]

    on = [strat.labels[k] for k, w in strat.weights.items() if w > 0 and s_last[k]]
    warn = [strat.labels[k] for k, w in strat.weights.items() if w < 0 and s_last[k]]
    if last.CHG_PCT >= 29:
        warn.append("상한가 마감 (매수 불가 가능성)")
    trades = backtest.next_day_trades(d, score, threshold, strategy.STOP_ATR)
    return Result(
        code=code, name=name, date=d.index[-1].strftime("%Y-%m-%d"), strategy=strat.name,
        close=last.Close, chg_pct=last.CHG_PCT, score=float(score.iloc[-1]),
        grade=strategy.grade(score.iloc[-1], threshold), signals_on=on, warnings=warn,
        plan=strategy.trade_plan(last), amount=last.AMOUNT, rsi=last.RSI,
        vol_ratio=last.VOL_RATIO, atr_pct=last.ATR_PCT,
        backtest=backtest.summarize(trades),
    )


def analyze(symbol: str, strat: strategy.Strategy | None = None,
            threshold: float | None = None, days: int = 1100) -> Result:
    code, name = data.resolve(symbol)
    return analyze_df(code, name, data.ohlcv(code, days), strat, threshold)
