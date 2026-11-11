"""단타 차트 분석기 실행 파일.

  1단계 - 내가 고른 종목 분석
    python main.py analyze 삼성전자 000660 에코프로 AAPL

  2단계 - 전 종목 스캔 후 추천
    python main.py scan                      # 거래대금 상위 500개 스캔, 상위 20개 추천
    python main.py scan --market KOSDAQ --top 30
    python main.py scan --limit 0            # 조건 맞는 전 종목 (오래 걸림)

  전략 검증 - 점수가 실제로 다음날 수익과 연결되는지 확인 (전략 수정 시 필수)
    python main.py validate --limit 150
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from daytrader import report
from daytrader.analyzer import analyze
from daytrader.scanner import scan
from daytrader import validate


def cmd_analyze(a) -> None:
    results = []
    for sym in a.symbols:
        try:
            r = analyze(sym, a.threshold)
        except Exception as e:
            print(f"[오류] {sym}: {e}")
            continue
        report.print_detail(r)
        results.append(r)
    if len(results) > 1:
        print("\n■ 점수 순위")
        results.sort(key=lambda r: r.score, reverse=True)
        report.print_table(results, len(results))
    if results and a.save:
        csv, htm = report.save(results, "종목분석")
        print(f"\n저장: {csv}\n      {htm}")
    print(f"\n※ {report.DISCLAIMER}")


def cmd_scan(a) -> None:
    def prog(i, n):
        print(f"\r스캔 중... {i}/{n}", end="", file=sys.stderr, flush=True)

    results, errors = scan(a.market, a.limit or None, a.min_amount, a.threshold, a.workers, prog)
    print(file=sys.stderr)
    picks = [r for r in results if r.score >= a.threshold
             and (r.backtest.get("평균수익%") is None or r.backtest["평균수익%"] > 0 or not a.require_edge)]
    print(f"\n■ 스캔 {len(results)}종목 (실패 {len(errors)}) → 기준점수 {a.threshold}점 이상 {len(picks)}종목\n")
    report.print_table(picks, a.top)
    for r in picks[: min(3, a.top)]:
        report.print_detail(r)
    if a.save:
        csv, htm = report.save(picks[: a.top], f"추천종목_{a.market}")
        print(f"저장: {csv}\n      {htm}")
    print(f"\n※ {report.DISCLAIMER}")


def cmd_validate(a) -> None:
    n, table, summary = validate.run(a.market, a.limit, a.min_amount, a.threshold, a.workers)
    print(f"\n■ 전략 검증: 거래대금 상위 {n}종목 × 최근 약 1년 일봉\n")
    with pd.option_context("display.unicode.east_asian_width", True, "display.width", 200):
        print(table.to_string())
    print(f"\n■ {a.threshold}점 이상 신호 → 다음날 단타(시가매수, ±0.5ATR 익절/손절, 비용 0.25%)")
    print(f"   {summary}")
    hi = table["익일시가→종가%"].iloc[-2:].mean()
    lo = table["익일시가→종가%"].iloc[:2].mean()
    if hi <= lo or (summary.get("평균수익%") or 0) <= 0:
        print("\n⚠ 판정: 현재 점수 체계는 다음날 수익을 예측하지 못합니다 (고득점 구간이 더 낫지 않음).")
        print("  → 추천 결과를 매매 근거로 쓰지 말고, 가중치/규칙을 바꿔 다시 검증하세요.")
    else:
        print("\n✓ 판정: 고득점 구간의 성과가 더 좋습니다. 단, 기간·종목을 바꿔 재검증하세요(과최적화 주의).")


def main() -> None:
    p = argparse.ArgumentParser(description="단타(익일) 차트 분석기")
    p.add_argument("--threshold", type=float, default=55, help="추천 기준 점수 (기본 55)")
    p.add_argument("--no-save", dest="save", action="store_false", help="리포트 파일 저장 안 함")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("analyze", help="입력한 종목 분석")
    s1.add_argument("symbols", nargs="+", help="종목명/코드/해외티커")
    s1.set_defaults(func=cmd_analyze)

    s2 = sub.add_parser("scan", help="전 종목 스캔 후 추천")
    s2.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    s2.add_argument("--limit", type=int, default=500, help="거래대금 상위 N개만 스캔 (0=전체)")
    s2.add_argument("--min-amount", type=float, default=30, help="최소 당일 거래대금(억원)")
    s2.add_argument("--top", type=int, default=20, help="추천 개수")
    s2.add_argument("--workers", type=int, default=8)
    s2.add_argument("--require-edge", action="store_true",
                    help="해당 종목 과거 검증 평균수익이 플러스인 경우만 추천")
    s2.set_defaults(func=cmd_scan)

    s3 = sub.add_parser("validate", help="점수 체계가 실제로 통하는지 과거 데이터로 검증")
    s3.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    s3.add_argument("--limit", type=int, default=150)
    s3.add_argument("--min-amount", type=float, default=30)
    s3.add_argument("--workers", type=int, default=8)
    s3.set_defaults(func=cmd_validate)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
