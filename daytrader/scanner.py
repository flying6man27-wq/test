"""전 종목 스캔 → 상위 추천."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from . import data
from .analyzer import Result, analyze_df

EXCLUDE_NAME = re.compile(r"스팩|ETN|리츠|(우|우B|우C|\d우B?)$")


def universe(market: str = "ALL", limit: int | None = 500,
             min_amount_eok: float = 30) -> pd.DataFrame:
    """스캔 대상: 우선주·스팩·ETN·리츠 제외, 당일 거래대금 하한, 거래대금 상위 limit개."""
    lst = data.krx_listing()
    mk = {"KOSPI": ["KOSPI"], "KOSDAQ": ["KOSDAQ", "KOSDAQ GLOBAL"],
          "ALL": ["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"]}[market.upper()]
    u = lst[lst.Market.isin(mk) & ~lst.Name.str.contains(EXCLUDE_NAME)]
    u = u[u.Amount >= min_amount_eok * 1e8].sort_values("Amount", ascending=False)
    return u.head(limit) if limit else u


def scan(market: str = "ALL", limit: int | None = 500, min_amount_eok: float = 30,
         threshold: float = 55, workers: int = 8, progress=None) -> tuple[list[Result], list[str]]:
    u = universe(market, limit, min_amount_eok)
    results, errors = [], []

    def job(code, name):
        return analyze_df(code, name, data.ohlcv(code), threshold)

    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(job, r.Code, r.Name): r.Name for r in u.itertuples()}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                results.append(f.result())
            except Exception as e:  # 데이터 부족·통신오류 등은 건너뜀
                errors.append(f"{futs[f]}: {e}")
            if progress:
                progress(i, len(futs))
    results.sort(key=lambda r: (r.score, r.backtest.get("평균수익%") or -99), reverse=True)
    return results, errors
