"""모의매매(페이퍼 트레이딩) 장부.

주문 흐름 (전략과 같은 규칙)
  예약  : 오늘(장 마감 후) 추천 종목에 '모의 매수' → 다음 거래일 시가에 체결 예정
  보유  : 다음 거래일 시가로 체결됨. 손절가 = 시가 - 1×ATR
  청산  : ① 장중 저가가 손절가에 닿으면 손절가에 매도
          ② 장 마감(15:40) 후에는 종가에 자동 매도 (당일 청산 원칙)
          ③ 화면의 [지금 매도] 버튼 → 현재가로 즉시 매도
실제 주문이 아니라 기록만 하며, 수익률에는 왕복 비용 0.25%를 차감한다.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pandas as pd

from . import data, journal
from .backtest import COST
from .strategy import STOP_ATR

FILE = journal.DIR / "paper_trades.csv"
COLS = ["id", "주문일", "코드", "종목", "점수", "투자금액", "ATR", "상태",
        "매수일", "매수가", "수량", "손절가", "매도일", "매도가", "청산사유", "수익%", "손익"]


def load() -> pd.DataFrame:
    df = journal._read(FILE)
    if df.empty:
        return pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    return df[COLS]


def save(df: pd.DataFrame) -> None:
    journal._write(df[COLS], FILE)


def place(code: str, name: str, signal_date: str, atr: float, amount: float, score: float | None = None) -> str:
    df = load()
    dup = df[(df["코드"] == code) & (df["주문일"] == signal_date) & (df["상태"].isin(["예약", "보유"]))]
    if len(dup):
        raise ValueError(f"{name}: 이미 같은 날 주문이 있습니다.")
    oid = uuid.uuid4().hex[:8]
    row = {c: None for c in COLS} | {"id": oid, "주문일": signal_date, "코드": code, "종목": name,
                                      "점수": score, "투자금액": amount, "ATR": atr, "상태": "예약"}
    save(pd.concat([df, pd.DataFrame([row])], ignore_index=True))
    return oid


def cancel(oid: str) -> None:
    df = load()
    save(df[~((df["id"] == oid) & (df["상태"] == "예약"))])


def _close(df, i, date, price, reason):
    buy = float(df.at[i, "매수가"])
    qty = float(df.at[i, "수량"])
    ret = (price / buy - 1) * 100 - COST
    df.loc[i, ["상태", "매도일", "매도가", "청산사유", "수익%", "손익"]] = [
        "청산", date, round(price, 2), reason, round(ret, 2), round(buy * qty * ret / 100)]


def refresh() -> pd.DataFrame:
    """시세를 가져와 예약→보유 체결, 손절/종가 청산을 반영. 보유 종목은 '현재가' 컬럼을 붙여 반환."""
    df = load()
    df["현재가"] = None
    for i, r in df[df["상태"].isin(["예약", "보유"])].iterrows():
        try:
            bars = data.ohlcv(r["코드"], days=20)
        except Exception:
            continue
        after = bars[bars.index > pd.Timestamp(r["주문일"])]
        if after.empty:
            continue
        b = after.iloc[0]
        bdate = after.index[0].strftime("%Y-%m-%d")
        if r["상태"] == "예약":
            qty = max(1, int(float(r["투자금액"]) // b.Open))
            df.loc[i, ["상태", "매수일", "매수가", "수량", "손절가"]] = [
                "보유", bdate, b.Open, qty, round(b.Open - STOP_ATR * float(r["ATR"]), 2)]
        stop = float(df.at[i, "손절가"])
        if b.Low <= stop:
            _close(df, i, bdate, stop, "손절")
        elif journal.bar_is_final(bdate):
            _close(df, i, bdate, b.Close, "종가 청산")
        else:
            df.at[i, "현재가"] = b.Close
    save(df)
    return df


def sell_now(oid: str) -> float:
    """보유 종목을 현재가로 매도."""
    df = load()
    idx = df.index[(df["id"] == oid) & (df["상태"] == "보유")]
    if not len(idx):
        raise ValueError("보유 중인 주문이 아닙니다.")
    i = idx[0]
    bars = data.ohlcv(df.at[i, "코드"], days=10)
    price = float(bars.Close.iloc[-1])
    _close(df, i, dt.datetime.now(journal.KST).strftime("%Y-%m-%d"), price, "수동 매도")
    save(df)
    return price


def stats(df: pd.DataFrame) -> dict:
    done = df[df["상태"] == "청산"]
    if done.empty:
        return {"거래수": 0, "승률%": None, "평균수익%": None, "총손익": 0}
    r = done["수익%"].astype(float)
    return {"거래수": len(done), "승률%": round((r > 0).mean() * 100, 1),
            "평균수익%": round(r.mean(), 2), "총손익": int(done["손익"].astype(float).sum())}
