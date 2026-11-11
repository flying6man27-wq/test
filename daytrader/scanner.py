"""전 종목 스캔 → 상위 추천."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from . import data, strategy
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


def scan(market: str = "ALL", limit: int | None = 300, min_amount_eok: float = 30,
         strat: strategy.Strategy | None = None, threshold: float | None = None,
         workers: int = 8, progress=None, days: int = 1100) -> tuple[list[Result], list[str]]:
    u = universe(market, limit, min_amount_eok)
    results, errors = [], []

    def job(code, name):
        return analyze_df(code, name, data.ohlcv(code, days), strat, threshold)

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


PANIC_SHARE = 10.0  # 스캔 종목 중 이 비율(%) 이상이 동시에 신호 → 시장 전반 투매일


def market_state(results: list[Result], threshold: float) -> tuple[float, bool]:
    """신호 종목 비율(%)과 '시장 전반 투매일' 여부.

    검증 결과 반등형 신호의 수익은 대부분 시장 전체가 투매한 날 다음날에서 나왔고,
    소수 종목만 신호가 난 날(개별 악재)은 평균 마이너스였다.
    """
    if not results:
        return 0.0, False
    share = sum(r.score >= threshold for r in results) / len(results) * 100
    return share, share >= PANIC_SHARE
