"""단기 매매 점수화 로직.

각 신호에 가중치를 주어 0~100점으로 환산한다. 모든 계산이 벡터 연산이라
과거 모든 날짜의 점수를 한 번에 구할 수 있고, 그대로 백테스트에 쓴다.
가중치(WEIGHTS)를 바꾸면 전략 성향을 조정할 수 있다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (신호키, 설명, 가중치)  — 음수는 감점 신호
SIGNALS = [
    ("trend",       "정배열 (종가 > 5일선 > 20일선)",             15),
    ("ma20_up",     "20일선 상승 중",                              5),
    ("macd_cross",  "MACD 골든크로스 (최근 3일 내)",              15),
    ("macd_rising", "MACD 히스토그램 확대",                        5),
    ("rsi_good",    "RSI 50~70 (상승 탄력 구간)",                 10),
    ("vol_surge",   "거래량 급증 (20일 평균 2배↑ + 양봉)",         15),
    ("vol_up",      "거래량 증가 (20일 평균 1.5배↑)",               5),
    ("breakout",    "20일 신고가 돌파",                           10),
    ("bb_break",    "볼린저 상단 돌파",                             5),
    ("sto_cross",   "스토캐스틱 골든크로스 (80 이하)",             10),
    ("strong_close","고가 부근 마감 (캔들 상단 25%)",              10),
    ("volatility",  "단타 적정 변동성 (ATR 2~8%)",                  5),
    ("overheat",    "과열 (RSI 80↑ 또는 당일 +20%↑)",             -15),
    ("upper_tail",  "긴 윗꼬리 (매도 압력)",                      -10),
    ("below_ma60",  "60일선 아래 (중기 하락 추세)",               -10),
]
WEIGHTS = {k: w for k, _, w in SIGNALS}
LABELS = {k: lbl for k, lbl, _ in SIGNALS}
MAX_SCORE = sum(w for w in WEIGHTS.values() if w > 0)


def signal_frame(d: pd.DataFrame) -> pd.DataFrame:
    """지표가 붙은 DataFrame → 날짜별 신호(True/False) 테이블."""
    s = pd.DataFrame(index=d.index)
    up_candle = d.Close > d.Open
    macd_x = (d.MACD > d.MACD_SIG) & (d.MACD.shift() <= d.MACD_SIG.shift())
    sto_x = (d.STO_K > d.STO_D) & (d.STO_K.shift() <= d.STO_D.shift()) & (d.STO_K < 80)

    s["trend"] = (d.Close > d.MA5) & (d.MA5 > d.MA20)
    s["ma20_up"] = d.MA20 > d.MA20.shift(3)
    s["macd_cross"] = macd_x.rolling(3).max().fillna(0).astype(bool)
    s["macd_rising"] = (d.MACD_HIST > d.MACD_HIST.shift()) & (d.MACD_HIST > 0)
    s["rsi_good"] = d.RSI.between(50, 70)
    s["vol_surge"] = (d.VOL_RATIO >= 2) & up_candle
    s["vol_up"] = (d.VOL_RATIO >= 1.5) & ~s["vol_surge"]
    s["breakout"] = d.Close > d.HIGH20
    s["bb_break"] = d.Close > d.BB_UP
    s["sto_cross"] = sto_x
    s["strong_close"] = d.CLOSE_POS >= 0.75
    s["volatility"] = d.ATR_PCT.between(2, 8)
    s["overheat"] = (d.RSI >= 80) | (d.CHG_PCT >= 20)
    s["upper_tail"] = (d.UPPER_SHADOW >= 0.5) & (d.CHG_PCT > 0)
    s["below_ma60"] = d.Close < d.MA60
    return s.fillna(False).astype(bool)


def score_series(sig: pd.DataFrame) -> pd.Series:
    raw = sum(sig[k].astype(int) * w for k, w in WEIGHTS.items())
    return (raw.clip(lower=0) / MAX_SCORE * 100).round(1)


def grade(score: float) -> str:
    if score >= 70:
        return "A (강한 매수 후보)"
    if score >= 55:
        return "B (매수 관심)"
    if score >= 40:
        return "C (관망)"
    return "D (매수 비추천)"


def trade_plan(last: pd.Series) -> dict:
    """ATR 기반 진입/목표/손절가. 진입가는 '오늘 종가' 기준 (다음날 시가 근처 진입 가정)."""
    entry, atr = last.Close, last.ATR
    stop = max(entry - 1.0 * atr, last.Low * 0.995)  # 1ATR 또는 당일 저가 하단 중 가까운 쪽
    return {
        "진입가": entry,
        "1차목표": entry + 1.0 * atr,
        "2차목표": entry + 2.0 * atr,
        "손절가": stop,
        "손익비": round((1.0 * atr) / max(entry - stop, 1e-9), 2),
    }
