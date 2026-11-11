"""매매 전략(점수 체계) 정의.

전략마다 신호 목록(SIGNALS)과 가중치가 있고, 신호 합계를 0~100점으로 환산한다.
모든 계산이 벡터 연산이라 과거 전체 날짜의 점수를 한 번에 구해 백테스트·검증에 쓴다.

공통 매매 방식 (단타): 오늘 장 마감 후 분석 → 다음 거래일 '시가 매수 → 당일 종가 매도'
  · 손절: 시가 - 1×ATR 에 닿으면 손절 (기본)

전략 목록
  reversal (기본) : 과매도 반등형. 2022.11~2026.11 거래대금 상위 285종목 검증에서
                    점수가 높을수록 다음날 장중 수익이 높았던 규칙들로 구성.
  momentum        : 돌파·거래량 추세형 (1차 버전). 검증 결과 예측력 없음 → 비교용으로만 유지.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Strategy:
    name: str
    title: str
    signals: list            # [(키, 설명, 가중치)], 음수 = 감점
    rules: Callable          # 지표 DataFrame → 신호 DataFrame(bool)
    default_threshold: float

    @property
    def weights(self) -> dict:
        return {k: w for k, _, w in self.signals}

    @property
    def labels(self) -> dict:
        return {k: lbl for k, lbl, _ in self.signals}

    @property
    def max_score(self) -> float:
        return sum(w for w in self.weights.values() if w > 0)

    def signal_frame(self, d: pd.DataFrame) -> pd.DataFrame:
        s = self.rules(d)
        return s[list(self.weights)].fillna(False).astype(bool)

    def score_series(self, sig: pd.DataFrame) -> pd.Series:
        raw = sum(sig[k].astype(int) * w for k, w in self.weights.items())
        return (raw.clip(lower=0) / self.max_score * 100).round(1)


# ── 반등형 (기본) ────────────────────────────────────────────────────────────
def _reversal_rules(d: pd.DataFrame) -> pd.DataFrame:
    s = pd.DataFrame(index=d.index)
    s["rsi_oversold"] = d.RSI < 30
    s["bb_below"] = d.Close < d.BB_LO
    s["crash"] = d.CHG_PCT <= -7
    s["weak_close"] = (d.CLOSE_POS <= 0.2) & (d.CHG_PCT < 0)
    s["rsi2_extreme"] = d.RSI2 < 10
    s["high_vol"] = d.ATR_PCT > 4
    s["surged"] = d.CHG_PCT >= 10
    s["low_vol"] = d.ATR_PCT <= 2
    return s


REVERSAL = Strategy(
    name="reversal",
    title="과매도 반등형",
    signals=[
        ("rsi_oversold", "RSI(14) 30 미만 (과매도)",                 25),
        ("bb_below",     "볼린저밴드 하단 이탈",                       20),
        ("crash",        "당일 급락 (-7% 이하)",                       20),
        ("high_vol",     "변동성 큼 (ATR 4% 초과, 반등 폭 기대)",       15),
        ("weak_close",   "저가 부근 마감 (캔들 하단 20%)",              10),
        ("rsi2_extreme", "RSI(2) 10 미만 (초단기 투매)",               10),
        ("surged",       "당일 +10% 이상 급등 (다음날 장중 약세 경향)", -30),
        ("low_vol",      "변동성 너무 작음 (ATR 2% 이하)",             -15),
    ],
    rules=_reversal_rules,
    default_threshold=60,
)


# ── 추세형 (1차 버전, 비교용) ──────────────────────────────────────────────
def _momentum_rules(d: pd.DataFrame) -> pd.DataFrame:
    s = pd.DataFrame(index=d.index)
    up_candle = d.Close > d.Open
    macd_x = (d.MACD > d.MACD_SIG) & (d.MACD.shift() <= d.MACD_SIG.shift())
    s["trend"] = (d.Close > d.MA5) & (d.MA5 > d.MA20)
    s["ma20_up"] = d.MA20 > d.MA20.shift(3)
    s["macd_cross"] = macd_x.rolling(3).max().fillna(0).astype(bool)
    s["macd_rising"] = (d.MACD_HIST > d.MACD_HIST.shift()) & (d.MACD_HIST > 0)
    s["rsi_good"] = d.RSI.between(50, 70)
    s["vol_surge"] = (d.VOL_RATIO >= 2) & up_candle
    s["vol_up"] = (d.VOL_RATIO >= 1.5) & ~s["vol_surge"]
    s["breakout"] = d.Close > d.HIGH20
    s["bb_break"] = d.Close > d.BB_UP
    s["sto_cross"] = (d.STO_K > d.STO_D) & (d.STO_K.shift() <= d.STO_D.shift()) & (d.STO_K < 80)
    s["strong_close"] = d.CLOSE_POS >= 0.75
    s["volatility"] = d.ATR_PCT.between(2, 8)
    s["overheat"] = (d.RSI >= 80) | (d.CHG_PCT >= 20)
    s["upper_tail"] = (d.UPPER_SHADOW >= 0.5) & (d.CHG_PCT > 0)
    s["below_ma60"] = d.Close < d.MA60
    return s


MOMENTUM = Strategy(
    name="momentum",
    title="돌파 추세형 (비교용)",
    signals=[
        ("trend",        "정배열 (종가 > 5일선 > 20일선)",  15),
        ("ma20_up",      "20일선 상승 중",                   5),
        ("macd_cross",   "MACD 골든크로스 (최근 3일 내)",   15),
        ("macd_rising",  "MACD 히스토그램 확대",             5),
        ("rsi_good",     "RSI 50~70",                       10),
        ("vol_surge",    "거래량 급증 (2배↑ + 양봉)",       15),
        ("vol_up",       "거래량 증가 (1.5배↑)",             5),
        ("breakout",     "20일 신고가 돌파",                10),
        ("bb_break",     "볼린저 상단 돌파",                 5),
        ("sto_cross",    "스토캐스틱 골든크로스",           10),
        ("strong_close", "고가 부근 마감",                  10),
        ("volatility",   "ATR 2~8%",                         5),
        ("overheat",     "과열 (RSI 80↑ 또는 +20%↑)",      -15),
        ("upper_tail",   "긴 윗꼬리",                      -10),
        ("below_ma60",   "60일선 아래",                    -10),
    ],
    rules=_momentum_rules,
    default_threshold=55,
)

STRATEGIES = {s.name: s for s in (REVERSAL, MOMENTUM)}
DEFAULT = "reversal"


def get(name: str | None = None) -> Strategy:
    return STRATEGIES[name or DEFAULT]


def grade(score: float, threshold: float) -> str:
    if score >= max(threshold + 15, 75):
        return "A (강한 후보)"
    if score >= threshold:
        return "B (매수 후보)"
    if score >= threshold - 20:
        return "C (관망)"
    return "D (해당 없음)"


STOP_ATR = 1.0


def trade_plan(last: pd.Series) -> dict:
    """다음날 시가 매수 → 당일 종가 매도. 시가를 모르므로 오늘 종가 기준 참고가를 제시."""
    ref, atr = last.Close, last.ATR
    return {
        "기준가": ref,
        "손절폭": STOP_ATR * atr,                 # 실제 손절가 = 다음날 시가 - 손절폭
        "참고손절가": ref - STOP_ATR * atr,
        "매도": "당일 종가 (장 마감 직전)",
    }
