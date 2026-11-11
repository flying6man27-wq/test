"""시세/종목 데이터 수집 (FinanceDataReader 기반: 국내 KRX + 미국 주식)."""
from __future__ import annotations

import datetime as dt
import time
from functools import lru_cache

import pandas as pd
import FinanceDataReader as fdr


@lru_cache(maxsize=1)
def krx_listing() -> pd.DataFrame:
    """KRX 전체 상장 종목 (당일 시세·거래대금 포함)."""
    for attempt in range(4):  # KRX 서버가 간헐적으로 응답 실패 → 재시도
        try:
            df = fdr.StockListing("KRX")
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    df["Code"] = df["Code"].astype(str).str.zfill(6)
    return df


def resolve(symbol: str) -> tuple[str, str]:
    """'삼성전자' / '005930' / 'AAPL' → (코드, 표시이름)."""
    s = symbol.strip()
    if s.isdigit():
        code = s.zfill(6)
        try:
            row = krx_listing().loc[lambda d: d.Code == code]
            return code, (row.Name.iloc[0] if len(row) else code)
        except Exception:
            return code, code
    if s.isascii():  # 해외 티커 (AAPL, TSLA ...)
        return s.upper(), s.upper()
    lst = krx_listing()
    exact = lst[lst.Name == s]
    if len(exact):
        return exact.Code.iloc[0], s
    part = lst[lst.Name.str.contains(s, regex=False)]
    if len(part):
        return part.Code.iloc[0], part.Name.iloc[0]
    raise ValueError(f"종목을 찾을 수 없습니다: {symbol}")


def ohlcv(code: str, days: int = 400) -> pd.DataFrame:
    """일봉 OHLCV. 컬럼: Open High Low Close Volume"""
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    for attempt in range(3):  # 일시적 통신 오류 재시도
        try:
            df = fdr.DataReader(code, start)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df = df[df["Volume"] > 0]  # 거래정지일 제거
    return df.astype(float)
