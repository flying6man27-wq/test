"""전진 검증(Forward test): 매일 스캔 결과를 기록하고, 다음 거래일 실제 결과와 비교.

과거 백테스트는 생존 편향·사후 규칙 선택 등의 한계가 있다. 앞으로 실제로 나온 신호가
실제로 어떤 성과를 냈는지 쌓아가는 것이 가장 확실한 검증이다.

파일 (journal/ 폴더)
  days.csv     스캔한 날마다 1줄: 시장 신호 비율, 투매일 여부
  signals.csv  기준 점수 이상 종목마다 1줄 (+ 다음날 결과가 나오면 결과 컬럼 채움)
매매 가정은 백테스트와 동일: 다음날 시가 매수 → 종가 매도, 손절 시가-1ATR, 비용 0.25%
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from . import data
from .analyzer import Result
from .backtest import COST
from .strategy import STOP_ATR

DIR = Path("journal")
DAYS, SIGNALS = DIR / "days.csv", DIR / "signals.csv"
KST = ZoneInfo("Asia/Seoul")
OUTCOME_COLS = ["결과일", "시가", "저가", "종가_익일", "손절가", "청산가", "결과", "수익%"]
SIGNAL_COLS = ["기준일", "전략", "코드", "종목", "점수", "종가", "등락%", "ATR", "투매일"] + OUTCOME_COLS


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"코드": str}, encoding="utf-8-sig")


def _write(df: pd.DataFrame, path: Path) -> None:
    DIR.mkdir(exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def bar_is_final(bar_date: str) -> bool:
    """당일 봉이면 장 마감(15:40 KST) 이후여야 확정."""
    now = dt.datetime.now(KST)
    return bar_date < now.strftime("%Y-%m-%d") or now.time() >= dt.time(15, 40)


def record(results: list[Result], strategy: str, threshold: float,
           share: float, panic: bool) -> tuple[int, str]:
    """스캔 결과 기록. 같은 날·전략을 다시 스캔하면 덮어쓴다. 반환: (기록 종목수, 기준일)"""
    if not results:
        return 0, ""
    day = max(r.date for r in results)
    days = _read(DAYS)
    if len(days):
        days = days[~((days["기준일"] == day) & (days["전략"] == strategy))]
    days = pd.concat([days, pd.DataFrame([{
        "기준일": day, "전략": strategy, "기준점수": threshold, "스캔종목수": len(results),
        "신호종목수": sum(r.score >= threshold for r in results),
        "신호비율%": round(share, 2), "투매일": bool(panic),
        "기록시각": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}])])
    _write(days.sort_values(["기준일", "전략"]), DAYS)

    picks = [r for r in results if r.score >= threshold and r.date == day and r.chg_pct < 29]
    sig = _read(SIGNALS)
    if sig.empty:
        sig = pd.DataFrame(columns=SIGNAL_COLS)  # 첫 실행: 빈 표라도 컬럼은 갖춘다
    else:
        sig = sig[~((sig["기준일"] == day) & (sig["전략"] == strategy))]
    new = pd.DataFrame(columns=SIGNAL_COLS, data=[{
        "기준일": day, "전략": strategy, "코드": r.code, "종목": r.name, "점수": r.score,
        "종가": r.close, "등락%": round(r.chg_pct, 2), "ATR": round(r.plan["손절폭"] / STOP_ATR, 4),
        "투매일": bool(panic), **{c: None for c in OUTCOME_COLS}} for r in picks])
    merged = pd.concat([x for x in (sig, new) if len(x)]) if len(sig) or len(new) else sig
    if len(merged):
        merged = merged.sort_values(["기준일", "전략", "점수"], ascending=[True, True, False])
    _write(merged, SIGNALS)
    return len(picks), day


def _outcome(code: str, day: str, atr: float) -> dict | None:
    start = (pd.Timestamp(day) + pd.Timedelta(days=1)).date()
    df = data.ohlcv(code, days=(dt.date.today() - start).days + 3)
    df = df[df.index > pd.Timestamp(day)]
    if df.empty:
        return None
    nxt = df.iloc[0]
    if not bar_is_final(df.index[0].strftime("%Y-%m-%d")):
        return None
    o, lo, c = nxt.Open, nxt.Low, nxt.Close
    stop = o - STOP_ATR * atr
    hit = lo <= stop
    exit_px = stop if hit else c
    return {"결과일": df.index[0].strftime("%Y-%m-%d"), "시가": o, "저가": lo, "종가_익일": c,
            "손절가": round(stop, 2), "청산가": round(exit_px, 2),
            "결과": "손절" if hit else "종가청산", "수익%": round((exit_px / o - 1) * 100 - COST, 2)}


def update() -> int:
    """결과가 비어 있는 신호의 다음날 결과를 채운다. 반환: 새로 채운 건수"""
    sig = _read(SIGNALS)
    if sig.empty:
        return 0
    filled = 0
    for i, row in sig[sig["결과일"].isna()].iterrows():
        try:
            out = _outcome(row["코드"], row["기준일"], row["ATR"])
        except Exception:
            continue
        if out:
            for k, v in out.items():
                sig.loc[i, k] = v
            filled += 1
    _write(sig, SIGNALS)
    return filled


def summary() -> dict | None:
    sig, days = _read(SIGNALS), _read(DAYS)
    if sig.empty and days.empty:
        return None
    done = sig[sig["결과일"].notna()].copy() if len(sig) else sig

    def stats(df):
        if df.empty:
            return {"거래수": 0, "승률%": None, "평균수익%": None}
        r = df["수익%"].astype(float)
        return {"거래수": len(df), "승률%": float(round((r > 0).mean() * 100, 1)),
                "평균수익%": float(round(r.mean(), 2))}

    # 하루에 여러 종목이면 같은 금액씩 나눠 산 것으로 보고 날짜별 평균 → 누적
    daily = done.groupby("기준일")["수익%"].mean() if len(done) else pd.Series(dtype=float)
    panic_daily = done[done["투매일"]].groupby("기준일")["수익%"].mean() if len(done) else daily
    return {
        "기록일수": days["기준일"].nunique() if len(days) else 0,
        "투매일수": int(days.drop_duplicates("기준일")["투매일"].sum()) if len(days) else 0,
        "결과대기": int(sig["결과일"].isna().sum()) if len(sig) else 0,
        "전체": stats(done),
        "투매일 신호": stats(done[done["투매일"]]) if len(done) else stats(done),
        "평상시 신호": stats(done[~done["투매일"]]) if len(done) else stats(done),
        "투매일만 매매 시 누적%": float(round(((1 + panic_daily / 100).prod() - 1) * 100, 2)) if len(panic_daily) else None,
        "모든 신호 매매 시 누적%": float(round(((1 + daily / 100).prod() - 1) * 100, 2)) if len(daily) else None,
        "최근": done.tail(15)[["기준일", "종목", "점수", "투매일", "결과", "수익%"]] if len(done) else None,
    }
