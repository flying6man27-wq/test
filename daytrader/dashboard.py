"""대시보드: 오늘 판정 · 추천 종목 · 시장 신호 비율 추이 · 전진 검증 성적을 HTML 한 장으로.

scan 이 남긴 journal/latest.json(오늘 결과)과 journal/days.csv·signals.csv(누적 기록)를 읽는다.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import webbrowser
from pathlib import Path

import pandas as pd

from . import journal
from .report import DISCLAIMER
from .scanner import PANIC_SHARE

LATEST = journal.DIR / "latest.json"
OUT = Path("reports") / "dashboard.html"


def save_latest(results, strategy: str, threshold: float, share: float, panic: bool, final: bool) -> None:
    picks = sorted((r for r in results if r.score >= threshold and r.chg_pct < 29),
                   key=lambda r: r.score, reverse=True)[:20]
    payload = {
        "기준일": max((r.date for r in results), default=""), "전략": strategy, "기준점수": threshold,
        "스캔종목수": len(results), "신호비율": round(share, 2), "투매일": bool(panic), "확정": bool(final),
        "생성": dt.datetime.now(journal.KST).strftime("%Y-%m-%d %H:%M"),
        "추천": [{"종목": r.name, "코드": r.code, "점수": r.score, "종가": r.close,
                 "등락": round(r.chg_pct, 2), "손절폭": round(r.plan["손절폭"], 1),
                 "과거승률": r.backtest.get("승률%"), "과거평균": r.backtest.get("평균수익%"),
                 "신호": r.signals_on} for r in picks],
    }
    journal.DIR.mkdir(exist_ok=True)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _e(x) -> str:
    return html.escape(str(x))


def _num(x, d=2, sign=False) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    return f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}"


def _price(x) -> str:
    return f"{x:,.0f}" if x >= 1000 else f"{x:,.2f}"


def _history_svg(days: pd.DataFrame) -> str:
    """최근 60일 신호 비율 막대 + 투매일 기준선 (단일 계열)."""
    d = days.drop_duplicates("기준일", keep="last").tail(60)
    if d.empty:
        return '<p class="muted">아직 기록이 없습니다. 매일 장 마감 후 실행하면 여기에 쌓입니다.</p>'
    W, H, pl, pr, pt, pb = 720, 220, 40, 12, 14, 28
    ymax = max(20.0, float(d["신호비율%"].max()) * 1.15)
    n = len(d)
    slot = (W - pl - pr) / max(n, 1)
    bw = max(2.0, min(18.0, slot - 2))  # 막대 사이 2px 이상 간격
    y = lambda v: pt + (H - pt - pb) * (1 - v / ymax)
    parts = []
    for t in (0, 10, 20, 30, 40, 50):
        if t <= ymax:
            parts.append(f'<line x1="{pl}" x2="{W-pr}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
                         f'<text x="{pl-6}" y="{y(t)+4:.1f}" class="tick" text-anchor="end">{t}%</text>')
    for i, r in enumerate(d.itertuples()):
        v = float(r._6)  # 신호비율%
        x = pl + i * slot + (slot - bw) / 2
        h = max(0.0, (H - pt - pb) - (y(v) - pt))
        tip = f"{r.기준일} · 신호 비율 {v:.1f}% · {'투매일' if r.투매일 else '평상시'}"
        rr = min(4.0, bw / 2, h)
        path = (f"M{x:.1f},{H-pb} V{H-pb-h+rr:.1f} Q{x:.1f},{H-pb-h:.1f} {x+rr:.1f},{H-pb-h:.1f} "
                f"H{x+bw-rr:.1f} Q{x+bw:.1f},{H-pb-h:.1f} {x+bw:.1f},{H-pb-h+rr:.1f} V{H-pb} Z") if h > 0 else ""
        mark = f'<path d="{path}" class="mark"/>' if path else ""
        parts.append(f'<g class="bar" data-tip="{_e(tip)}"><rect x="{x-1:.1f}" y="{pt}" width="{bw+2:.1f}" '
                     f'height="{H-pt-pb}" class="hit"/>{mark}</g>')
    ty = y(PANIC_SHARE)
    parts.append(f'<line x1="{pl}" x2="{W-pr}" y1="{ty:.1f}" y2="{ty:.1f}" class="thr"/>'
                 f'<text x="{W-pr}" y="{ty-5:.1f}" class="thr-l" text-anchor="end">투매일 기준 {PANIC_SHARE:g}%</text>')
    first, last = d["기준일"].iloc[0], d["기준일"].iloc[-1]
    parts.append(f'<text x="{pl}" y="{H-8}" class="tick">{_e(first)}</text>'
                 f'<text x="{W-pr}" y="{H-8}" class="tick" text-anchor="end">{_e(last)}</text>')
    rows = "".join(f"<tr><td>{_e(r.기준일)}</td><td>{float(r._6):.1f}%</td><td>{'투매일' if r.투매일 else '평상시'}</td></tr>"
                   for r in d.iloc[::-1].itertuples())
    return (f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="최근 시장 신호 비율">{"".join(parts)}</svg>'
            f'<details><summary>표로 보기</summary><div class="scroll"><table class="tbl small"><thead><tr><th>기준일</th><th>신호 비율</th>'
            f'<th>판정</th></tr></thead><tbody>{rows}</tbody></table></div></details>')


def build(open_browser: bool = True) -> Path:
    latest = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else None
    days = journal._read(journal.DAYS)
    s = journal.summary()

    # ── 오늘 판정 배너
    if not latest:
        banner = ('<div class="banner info"><span class="ico">ℹ️</span><div><b>아직 scan 결과가 없습니다</b>'
                  '<p>장 마감 후(16시 이후) run_daily.bat 을 실행하세요.</p></div></div>')
        picks_html = ""
    else:
        stale = "" if latest["확정"] else ('<p class="warn-note">⚠ 장 마감 전에 실행한 결과입니다. '
                                          '캔들이 미완성이라 16시 이후 다시 실행하세요.</p>')
        if latest["투매일"]:
            banner = (f'<div class="banner good"><span class="ico">✅</span><div><b>매매일: 시장 전반 투매일</b>'
                      f'<p>신호 비율 {latest["신호비율"]:.1f}% (기준 {PANIC_SHARE:g}% 이상). 과거 이런 날 다음날 반등 매매는 '
                      f'평균 +1.85%, 승률 63%였습니다. 단, 하락이 이어지면 크게 잃을 수 있으니 여러 종목에 나눠 소액으로.</p>'
                      f'</div></div>')
        else:
            banner = (f'<div class="banner bad"><span class="ico">⛔</span><div><b>쉬는 날: 매매 비추천</b>'
                      f'<p>신호 비율 {latest["신호비율"]:.1f}% (기준 {PANIC_SHARE:g}% 미만). 소수 종목만 신호가 난 날은 '
                      f'과거 평균이 마이너스였습니다. 아래 목록은 참고용입니다.</p></div></div>')
        banner += stale
        rows = "".join(
            f'<tr><td class="l"><b>{_e(p["종목"])}</b><small>{_e(p["코드"])}</small></td>'
            f'<td><span class="score">{p["점수"]:.0f}</span></td>'
            f'<td class="{"dn" if p["등락"] < 0 else "up"}">{_num(p["등락"], sign=True)}%</td>'
            f'<td>{_price(p["종가"])}</td><td>{_price(p["손절폭"])}</td>'
            f'<td>{_num(p["과거승률"], 1)}%</td><td>{_num(p["과거평균"], sign=True)}%</td>'
            f'<td class="l sig">{_e(", ".join(p["신호"]))}</td></tr>' for p in latest["추천"])
        picks_html = (
            f'<section><h2>추천 종목 <span class="muted">{_e(latest["기준일"])} 기준 · {latest["기준점수"]:g}점 이상 · '
            f'{len(latest["추천"])}종목</span></h2>'
            + (f'<div class="scroll"><table class="tbl"><thead><tr><th class="l">종목</th><th>점수</th><th>등락</th>'
               f'<th>종가</th><th>손절폭</th><th>과거 승률</th><th>과거 평균</th><th class="l">신호</th></tr></thead>'
               f'<tbody>{rows}</tbody></table></div>'
               '<p class="muted">매매 방법: 다음 거래일 <b>시가 매수 → 장 마감 직전 매도</b>. 매수가 − 손절폭에 닿으면 손절. '
               '과거 승률·평균은 그 종목 최근 3년 같은 신호의 결과(비용 0.25% 차감).</p>'
               if latest["추천"] else '<p class="muted">오늘은 기준 점수 이상인 종목이 없습니다.</p>')
            + '</section>')

    # ── 전진 검증 성적
    if s:
        def tile(title, st, note=""):
            return (f'<div class="tile"><div class="t">{title}</div>'
                    f'<div class="v">{_num(st["평균수익%"], sign=True)}<span>%</span></div>'
                    f'<div class="m">거래 {st["거래수"]}건 · 승률 {_num(st["승률%"], 1)}%</div>{note}</div>')
        recent = s["최근"]
        rrows = "" if recent is None else "".join(
            f'<tr><td>{_e(r.기준일)}</td><td class="l">{_e(r.종목)}</td><td>{r.점수:.0f}</td>'
            f'<td>{"투매일" if r.투매일 else "평상시"}</td><td>{_e(r.결과)}</td>'
            f'<td class="{"up" if r._6 > 0 else "dn"}">{float(r._6):+.2f}%</td></tr>'
            for r in recent.iloc[::-1].itertuples())
        enough = s["투매일 신호"]["거래수"] >= 30
        track_html = (
            '<section><h2>전진 검증 성적 <span class="muted">실제로 기록된 신호의 다음날 결과</span></h2>'
            f'<div class="tiles">{tile("투매일 신호", s["투매일 신호"], "<div class=m>과거 기대치 +1.85%</div>")}'
            f'{tile("평상시 신호", s["평상시 신호"], "<div class=m>과거 기대치 약 0% 이하</div>")}'
            f'<div class="tile"><div class="t">투매일에만 매매 시 누적</div>'
            f'<div class="v">{_num(s["투매일만 매매 시 누적%"], sign=True)}<span>%</span></div>'
            f'<div class="m">기록 {s["기록일수"]}일 · 투매일 {s["투매일수"]}일 · 결과 대기 {s["결과대기"]}건</div></div></div>'
            + ('' if enough else '<p class="warn-note">⚠ 투매일 거래가 30건 미만이라 아직 판단하기 이릅니다. '
                                  '그때까지는 실제 돈 없이 기록만 지켜보세요.</p>')
            + (f'<details open><summary>최근 결과</summary><div class="scroll"><table class="tbl small"><thead><tr><th>기준일</th>'
               f'<th class="l">종목</th><th>점수</th><th>구분</th><th>결과</th><th>수익</th></tr></thead>'
               f'<tbody>{rrows}</tbody></table></div></details>' if rrows else
               '<p class="muted">아직 결과가 나온 신호가 없습니다. 다음 거래일 장 마감 후 확인됩니다.</p>')
            + '</section>')
    else:
        track_html = ('<section><h2>전진 검증 성적</h2><p class="muted">아직 기록이 없습니다. '
                      '매일 장 마감 후 run_daily.bat 을 실행하면 쌓입니다.</p></section>')

    hist_html = (f'<section><h2>시장 신호 비율 추이 <span class="muted">최근 60일 · 막대가 기준선을 넘으면 투매일</span></h2>'
                 f'{_history_svg(days)}</section>')

    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>단타 대시보드</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f4f4f2;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#7a7975;--line:#e4e3df;
--series:#2a78d6;--good:#0ca30c;--bad:#d03b3b;--good-bg:#e9f6e9;--bad-bg:#fbeaea;--info-bg:#eaf1fb;
--up:#d03b3b;--down:#2a78d6;--warn:#8a5a00;--warn-bg:#fff4dc}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#121211;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--muted:#9a998f;--line:#2e2e2b;--series:#3987e5;--good-bg:#132a13;--bad-bg:#2e1616;--info-bg:#15233a;--up:#e66767;
--down:#5598e7;--warn:#fab219;--warn-bg:#2d2410}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Noto Sans KR','Malgun Gothic',sans-serif;
word-break:keep-all;line-height:1.55}}
.wrap{{max-width:1040px;margin:0 auto;padding:24px 16px 48px}}
header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
h1{{font-size:22px;margin:0}}h2{{font-size:16px;margin:0 0 12px}}.muted{{color:var(--muted);font-weight:400;font-size:13px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}}
.banner{{display:flex;gap:14px;align-items:flex-start;border-radius:12px;padding:18px;margin-bottom:12px;border:1px solid var(--line)}}
.banner .ico{{font-size:28px;line-height:1}}.banner b{{font-size:18px}}.banner p{{margin:4px 0 0;color:var(--ink2)}}
.banner.good{{background:var(--good-bg);border-left:6px solid var(--good)}}.banner.bad{{background:var(--bad-bg);border-left:6px solid var(--bad)}}
.banner.info{{background:var(--info-bg)}}
.warn-note{{background:var(--warn-bg);color:var(--warn);padding:8px 12px;border-radius:8px;font-size:13px;margin:0 0 12px}}
.scroll{{overflow-x:auto}}.tbl{{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}}
.tbl th,.tbl td{{padding:8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
.tbl th{{color:var(--ink2);font-weight:500;font-size:12px}}.tbl .l{{text-align:left}}.tbl small{{display:block;color:var(--muted)}}
.tbl.small{{font-size:13px;margin-top:8px}}.sig{{white-space:normal!important;min-width:220px;color:var(--ink2);font-size:12px}}
.score{{display:inline-block;min-width:34px;padding:1px 8px;border-radius:10px;background:var(--series);color:#fff;font-weight:700;text-align:center}}
.up{{color:var(--up)}}.dn{{color:var(--down)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:12px}}
.tile{{border:1px solid var(--line);border-radius:10px;padding:14px}}.tile .t{{color:var(--ink2);font-size:13px}}
.tile .v{{font-size:30px;font-weight:700;margin:4px 0}}.tile .v span{{font-size:16px;color:var(--ink2);margin-left:2px}}
.tile .m{{color:var(--muted);font-size:12px}}
.chart{{width:100%;height:auto;display:block}}.grid{{stroke:var(--line);stroke-width:1}}
.tick{{fill:var(--muted);font-size:11px}}.mark{{fill:var(--series)}}.hit{{fill:transparent}}
.bar:hover .mark{{opacity:.75}}.thr{{stroke:var(--ink2);stroke-width:1.5;stroke-dasharray:4 4}}
.thr-l{{fill:var(--ink2);font-size:11px}}
#tip{{position:fixed;pointer-events:none;background:var(--ink);color:var(--card);padding:6px 10px;border-radius:6px;
font-size:12px;opacity:0;transition:opacity .1s}}
details summary{{cursor:pointer;color:var(--ink2);font-size:13px;margin-top:8px}}
footer{{color:var(--muted);font-size:12px;text-align:center}}
</style></head><body><div class="wrap">
<header><h1>단타 대시보드</h1><span class="muted">{_e(latest["생성"] if latest else "")} 업데이트 · 과매도 반등형 전략</span></header>
{banner}{picks_html}{hist_html}{track_html}
<footer>⚠ {_e(DISCLAIMER)}</footer></div><div id="tip"></div>
<script>
const tip=document.getElementById('tip');
document.querySelectorAll('.bar').forEach(b=>{{
 b.addEventListener('mousemove',e=>{{tip.textContent=b.dataset.tip;tip.style.opacity=1;
  tip.style.left=Math.min(e.clientX+12,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(e.clientY-36)+'px';}});
 b.addEventListener('mouseleave',()=>tip.style.opacity=0);}});
</script></body></html>"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    if open_browser:
        try:
            webbrowser.open(OUT.resolve().as_uri())
        except Exception:
            pass
    return OUT
