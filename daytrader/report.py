"""콘솔 출력 + HTML/CSV 리포트."""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

import pandas as pd

from .analyzer import Result

DISCLAIMER = ("본 결과는 과거 차트 패턴에 기반한 참고용 신호이며 수익을 보장하지 않습니다. "
              "실제 투자 판단과 손실 책임은 투자자 본인에게 있습니다.")


def _fmt(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "-"
    if isinstance(x, float):
        return f"{x:,.2f}" if abs(x) < 1000 else f"{x:,.0f}"
    return str(x)


def print_detail(r: Result) -> None:
    p, b = r.plan, r.backtest
    unit = "억원" if r.code.isdigit() else "억(현지통화)"
    print("=" * 64)
    print(f" {r.name} ({r.code})   기준일 {r.date}")
    print("=" * 64)
    print(f" 종가 {_fmt(r.close)}  ({r.chg_pct:+.2f}%)   거래대금 {r.amount/1e8:,.0f}{unit}")
    print(f" ▶ 점수: {r.score:.0f}/100   등급: {r.grade}")
    print(f"   RSI {r.rsi:.1f} | 거래량 {r.vol_ratio:.1f}배 | 일평균 변동폭(ATR) {r.atr_pct:.1f}%")
    print("\n [긍정 신호]")
    for s in r.signals_on or ["(없음)"]:
        print(f"   ✓ {s}")
    print(" [주의 신호]")
    for s in r.warnings or ["(없음)"]:
        print(f"   ! {s}")
    print("\n [매매 방법 - 다음 거래일]")
    print(f"   시가 매수 → 장 마감 직전 매도 (당일 청산)")
    print(f"   손절: 매수가 - {_fmt(p['손절폭'])}  (오늘 종가 기준이면 {_fmt(p['참고손절가'])})")
    print("\n [이 종목 과거 검증 - 같은 기준 이상 신호 → 다음날 시가매수·종가매도, 비용 차감]")
    if b.get("거래수"):
        print(f"   신호 {b['거래수']}회 | 승률 {b['승률%']}% | 평균 {b['평균수익%']}%")
    else:
        print("   해당 기간 신호 없음")
    print()


def print_table(results: list[Result], top: int) -> None:
    if not results:
        print("결과 없음")
        return
    df = pd.DataFrame([r.row() for r in results[:top]])
    cols = ["종목", "코드", "점수", "등급", "등락%", "RSI", "거래량배수", "거래대금(억)",
            "ATR%", "손절폭", "과거승률%", "과거평균%", "과거거래수"]
    with pd.option_context("display.max_columns", None, "display.width", 250,
                           "display.unicode.east_asian_width", True):
        print(df[cols].to_string(index=False))


def save(results: list[Result], title: str, out_dir: str = "reports") -> tuple[Path, Path]:
    Path(out_dir).mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    df = pd.DataFrame([r.row() for r in results])
    csv = Path(out_dir) / f"{title}_{stamp}.csv"
    df.to_csv(csv, index=False, encoding="utf-8-sig")  # 엑셀에서 한글 깨짐 방지

    rows = []
    for r in results:
        cls = {"A": "a", "B": "b", "C": "c"}.get(r.grade[0], "d")
        rr = r.row()
        rows.append(
            f"<tr><td class='nm'>{html.escape(r.name)}<small>{r.code}</small></td>"
            f"<td><span class='g {cls}'>{r.score:.0f}</span></td>"
            f"<td class='{'up' if r.chg_pct>0 else 'dn'}'>{r.chg_pct:+.2f}%</td>"
            f"<td>{_fmt(r.close)}</td><td>{_fmt(rr['ATR%'])}</td><td>{_fmt(rr['손절폭'])}</td>"
            f"<td>{_fmt(rr['과거승률%'])}</td><td>{_fmt(rr['과거평균%'])}</td>"
            f"<td class='sig'>{html.escape(rr['주요신호'])}"
            f"{'<br><em>' + html.escape(rr['주의']) + '</em>' if rr['주의'] else ''}</td></tr>")
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
<style>
body{{font-family:'Noto Sans KR',sans-serif;word-break:keep-all;margin:24px;color:#1d2433;background:#fff}}
h1{{font-size:20px}} p.note{{color:#666;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border-bottom:1px solid #e3e6ec;padding:8px 6px;text-align:right;vertical-align:top}}
th{{background:#f4f6fa;position:sticky;top:0}} td.nm,td.sig{{text-align:left}}
td.nm small{{display:block;color:#888}} td.sig{{max-width:420px;color:#334}} td.sig em{{color:#c0392b;font-style:normal}}
.g{{display:inline-block;min-width:34px;padding:2px 6px;border-radius:10px;color:#fff;text-align:center;font-weight:700}}
.a{{background:#1e8e3e}}.b{{background:#5b8def}}.c{{background:#9aa0a6}}.d{{background:#c7cbd1}}
.up{{color:#d93025}}.dn{{color:#1a73e8}}
@media print{{tr{{page-break-inside:avoid}}}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="note">생성 {dt.datetime.now():%Y-%m-%d %H:%M} · 매매: 다음날 시가 매수 → 당일 종가 매도, 손절 = 매수가 - 손절폭 · 과거승률/평균은 해당 종목 최근 3년 동일 신호 결과(비용 0.25% 차감)</p>
<table><thead><tr><th style="text-align:left">종목</th><th>점수</th><th>등락</th><th>종가</th><th>ATR%</th><th>손절폭</th>
<th>과거승률%</th><th>과거평균%</th><th style="text-align:left">신호</th></tr></thead><tbody>
{''.join(rows)}</tbody></table>
<p class="note">⚠ {DISCLAIMER}</p></body></html>"""
    htm = Path(out_dir) / f"{title}_{stamp}.html"
    htm.write_text(page, encoding="utf-8")
    return csv, htm
