"""단타 차트 분석기 실행 파일.

매매 방식: 장 마감 후 실행 → 다음 거래일 '시가 매수 → 장 마감 직전 매도' (당일 청산)

  1단계 - 내가 고른 종목 분석
    python main.py analyze 삼성전자 000660 에코프로

  2단계 - 전 종목 스캔 후 추천
    python main.py scan                      # 거래대금 상위 300개 스캔 → 시장 상태 판정 + 추천
    python main.py scan --market KOSDAQ --top 30

  전진 검증 - scan 기록과 다음날 실제 결과 비교 (매일 scan 후 누적)
    python main.py track

  전략 검증 - 점수가 실제로 다음날 수익과 연결되는지 확인 (전략 수정 시 필수)
    python main.py validate
    python main.py --strategy momentum validate   # 1차(추세형) 전략과 비교
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from daytrader import journal, report, strategy, validate
from daytrader.analyzer import analyze
from daytrader.scanner import PANIC_SHARE, market_state, scan

pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 250)


def _strat_line(st, th):
    print(f"[전략] {st.title} ({st.name}) · 추천 기준 {th:g}점 이상\n")


def cmd_analyze(a, st, th) -> None:
    _strat_line(st, th)
    if st.name == "reversal":
        print("※ 반등형 신호는 '시장 전반 투매일'에만 과거 성과가 플러스였습니다.")
        print("  오늘이 그런 날인지는 scan 명령으로 확인하세요.\n")
    results = []
    for sym in a.symbols:
        try:
            r = analyze(sym, st, th)
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


def cmd_scan(a, st, th) -> None:
    _strat_line(st, th)

    def prog(i, n):
        print(f"\r스캔 중... {i}/{n}", end="", file=sys.stderr, flush=True)

    results, errors = scan(a.market, a.limit or None, a.min_amount, st, th, a.workers, prog)
    print(file=sys.stderr)
    picks = [r for r in results if r.score >= th and r.chg_pct < 29]
    print(f"\n■ 스캔 {len(results)}종목 (실패 {len(errors)}) → 기준 {th:g}점 이상 {len(picks)}종목\n")
    share, panic = market_state(results, th)
    if st.name == "reversal":
        print(f"■ 시장 상태: 신호 종목 비율 {share:.1f}% (투매일 기준 {PANIC_SHARE:g}% 이상)")
        if panic:
            print("  → ✅ 시장 전반 투매일입니다. 과거 이런 날의 다음날 반등 매매는 평균 플러스였습니다.")
            print("     단, 하락이 며칠 더 이어진 경우(예: 2024-08, 2025-04) 큰 손실이 났습니다. 비중을 나눠서 하세요.\n")
        else:
            print("  → ⛔ 오늘은 매매 비추천일입니다. 소수 종목만 신호가 난 날은 과거 평균이 마이너스였습니다.")
            print("     아래 목록은 참고용입니다.\n")
    if not picks:
        print("오늘은 조건에 맞는 종목이 없습니다.")
    report.print_table(picks, a.top)
    for r in picks[: min(3, a.top)]:
        report.print_detail(r)
    if a.save and picks:
        csv, htm = report.save(picks[: a.top], f"추천종목_{a.market}")
        print(f"저장: {csv}\n      {htm}")
    if a.journal and results:
        day = max(r.date for r in results)
        if journal.bar_is_final(day) or a.force:
            n, day = journal.record(results, st.name, th, share, panic)
            print(f"\n📒 전진 검증 기록: {day} · 신호 {n}종목 → journal/ (다음날 장 마감 후 track으로 결과 확인)")
        else:
            print("\n📒 장 마감(15:40) 전이라 기록하지 않았습니다. 마감 후 다시 scan 하세요.")
    print(f"\n※ {report.DISCLAIMER}")


def cmd_track(a, st, th) -> None:
    n = journal.update()
    print(f"■ 전진 검증: 새로 확인된 결과 {n}건\n")
    s = journal.summary()
    if not s:
        print("아직 기록이 없습니다. 매일 장 마감 후 scan 을 실행하면 자동으로 기록됩니다.")
        return
    print(f"기록한 날 {s['기록일수']}일 (그중 투매일 {s['투매일수']}일) · 결과 대기 {s['결과대기']}건\n")
    for k in ["투매일 신호", "평상시 신호", "전체"]:
        print(f"  {k:<8}: {s[k]}")
    print(f"\n  투매일에만 매매했다면 누적: {s['투매일만 매매 시 누적%']}%")
    print(f"  모든 신호를 매매했다면 누적: {s['모든 신호 매매 시 누적%']}%")
    print("\n  [과거 백테스트 기대치] 투매일 평균 +1.85% / 승률 63% · 평상시 약 0% 또는 마이너스")
    if s["투매일 신호"]["거래수"] < 30:
        print("  ※ 투매일 거래가 30건 미만이라 아직 판단하기 이릅니다. 기록을 계속 쌓으세요.")
    if s["최근"] is not None:
        print("\n[최근 결과]")
        print(s["최근"].to_string(index=False))


def cmd_validate(a, st, th) -> None:
    _strat_line(st, th)
    print("검증 중... (종목 수에 따라 1~3분)", file=sys.stderr)
    r = validate.run(a.market, a.limit, a.min_amount, st, th, a.workers, a.years, a.split)
    print(f"■ 거래대금 상위 {r['n_stocks']}종목 · {r['start']} ~ {r['end']} · 앞/뒤 기간 경계 {r['split']}")
    print("  (다음날 시가 매수 → 종가 매도 기준 / 초과% = 같은 날 전체 종목 평균 대비)\n")
    for key, title in [("table_early", "앞 기간"), ("table_late", "뒤 기간"), ("table_all", "전체")]:
        print(f"[{title}]")
        print(r[key].to_string(), "\n")
    print(f"■ {th:g}점 이상 → 실제 매매 규칙(손절 1ATR, 비용 0.25%) 백테스트")
    print(f"   앞 기간: {r['bt_early']}\n   뒤 기간: {r['bt_late']}\n   전체   : {r['bt_all']}")
    print("\n[연도별]")
    print(r["yearly"].to_string())
    print("\n[같은 날 신호가 난 종목 비율별] - 시장 전반 투매일인지에 따라 성과가 갈림")
    print(r["by_share"].to_string())
    print(f"   신호 비율 10% 이상인 날(투매일): {r['panic_days']}")
    ok, msg = validate.verdict(r)
    print(f"\n{msg}")
    if ok:
        print("✓ 판정: 앞·뒤 기간 모두 고득점 구간이 시장 평균보다 좋았고 비용 차감 후에도 플러스입니다.")
        print("  단, 과거 성과가 미래를 보장하지 않습니다. 소액·모의 매매로 먼저 확인하세요.")
    else:
        print("⚠ 판정: 통과하지 못했습니다. 이 점수로 추천하는 것은 근거가 부족합니다.")


def main() -> None:
    p = argparse.ArgumentParser(description="단타(익일 당일청산) 차트 분석기")
    p.add_argument("--strategy", default=strategy.DEFAULT, choices=list(strategy.STRATEGIES),
                   help="reversal=과매도 반등형(기본), momentum=추세형(비교용)")
    p.add_argument("--threshold", type=float, help="추천 기준 점수 (기본: 전략별 값)")
    p.add_argument("--no-save", dest="save", action="store_false", help="리포트 파일 저장 안 함")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("analyze", help="입력한 종목 분석")
    s1.add_argument("symbols", nargs="+", help="종목명/코드/해외티커")
    s1.set_defaults(func=cmd_analyze)

    s2 = sub.add_parser("scan", help="전 종목 스캔 후 추천")
    s2.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    s2.add_argument("--limit", type=int, default=300, help="거래대금 상위 N개만 스캔 (0=전체)")
    s2.add_argument("--min-amount", type=float, default=30, help="최소 당일 거래대금(억원)")
    s2.add_argument("--top", type=int, default=20, help="추천 개수")
    s2.add_argument("--workers", type=int, default=8)
    s2.add_argument("--no-journal", dest="journal", action="store_false", help="전진 검증 기록 안 함")
    s2.add_argument("--force", action="store_true", help="장 마감 전이어도 기록")
    s2.set_defaults(func=cmd_scan)

    s4 = sub.add_parser("track", help="전진 검증: 기록한 신호의 다음날 실제 결과 확인")
    s4.set_defaults(func=cmd_track)

    s3 = sub.add_parser("validate", help="점수 체계가 실제로 통하는지 과거 데이터로 검증")
    s3.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    s3.add_argument("--limit", type=int, default=300)
    s3.add_argument("--min-amount", type=float, default=30)
    s3.add_argument("--years", type=float, default=4)
    s3.add_argument("--split", help="앞/뒤 기간 경계일 (예: 2025-07-01, 기본: 전체의 60% 지점)")
    s3.add_argument("--workers", type=int, default=8)
    s3.set_defaults(func=cmd_validate)

    a = p.parse_args()
    st = strategy.get(a.strategy)
    th = st.default_threshold if a.threshold is None else a.threshold
    a.func(a, st, th)


if __name__ == "__main__":
    main()
