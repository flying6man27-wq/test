"""단타 트레이딩 화면 (Streamlit).

실행: 앱실행.bat 더블클릭  (또는  python -m streamlit run app.py)
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from daytrader import __version__, dashboard, data, journal, paper, strategy
from daytrader.analyzer import analyze_df
from daytrader.indicators import add_indicators
from daytrader.report import DISCLAIMER
from daytrader.scanner import PANIC_SHARE, market_state, scan

st.set_page_config(page_title="단타 트레이딩", page_icon="📈", layout="wide")
st.markdown("""<style>
html, body, [class*="css"] {word-break: keep-all;}
div[data-testid="stMetricValue"] {font-size: 1.6rem;}
.banner {border-radius: 10px; padding: 14px 18px; margin: 4px 0 12px; border-left: 6px solid;}
.banner b {font-size: 1.15rem;}
.good {background: rgba(12,163,12,.10); border-color: #0ca30c;}
.bad  {background: rgba(208,59,59,.10); border-color: #d03b3b;}
.info {background: rgba(42,120,214,.10); border-color: #2a78d6;}
</style>""", unsafe_allow_html=True)

STRAT = strategy.get("reversal")
UP, DOWN, SERIES = "#d03b3b", "#2a78d6", "#2a78d6"


# ── 공용 ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_bars(code: str, days: int = 1100) -> pd.DataFrame:
    return data.ohlcv(code, days)


@st.cache_data(ttl=3600, show_spinner=False)
def resolve(sym: str):
    return data.resolve(sym)


def banner(kind: str, title: str, body: str, icon: str) -> None:
    st.markdown(f'<div class="banner {kind}">{icon} <b>{title}</b><br>{body}</div>', unsafe_allow_html=True)


def candle_chart(code: str, name: str, days: int = 120) -> go.Figure:
    d = add_indicators(load_bars(code)).tail(days)
    sc = STRAT.score_series(STRAT.signal_frame(add_indicators(load_bars(code)))).tail(days)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.index, y=d.BB_UP, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=d.index, y=d.BB_LO, line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(128,128,128,.12)", name="볼린저밴드", hoverinfo="skip"))
    fig.add_trace(go.Candlestick(x=d.index, open=d.Open, high=d.High, low=d.Low, close=d.Close, name="일봉",
                                 increasing=dict(line=dict(color=UP), fillcolor=UP),
                                 decreasing=dict(line=dict(color=DOWN), fillcolor=DOWN)))
    fig.add_trace(go.Scatter(x=d.index, y=d.MA20, name="20일선", line=dict(color="#8a8a85", width=1.5)))
    sig = sc >= STRAT.default_threshold
    if sig.any():
        fig.add_trace(go.Scatter(x=d.index[sig], y=d.Low[sig] * 0.97, mode="markers", name="매수 신호",
                                 marker=dict(symbol="triangle-up", size=11, color="#eda100",
                                             line=dict(width=1, color="#5a3d00"))))
    fig.update_layout(title=f"{name} ({code}) · 최근 {days}일", height=430, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                      hovermode="x unified")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def buy_box(code: str, name: str, date: str, atr: float, score: float, key: str) -> None:
    c1, c2 = st.columns([2, 1])
    amt = c1.number_input("투자 금액 (원)", min_value=10000, value=1_000_000, step=100_000, key=f"amt_{key}")
    c2.write("")
    c2.write("")
    if c2.button("🛒 모의 매수 예약", key=f"buy_{key}", type="primary", use_container_width=True):
        try:
            paper.place(code, name, date, atr, amt, score)
            st.toast(f"{name} 모의 매수 예약 완료 → 다음 거래일 시가에 체결됩니다.", icon="✅")
        except ValueError as e:
            st.warning(str(e))
    st.caption("다음 거래일 **시가에 매수**되고, 손절가(시가 − 1×ATR)에 닿거나 **장 마감 시 자동 매도**됩니다. "
               "실제 주문이 아닌 모의 기록입니다.")


def load_latest():
    return json.loads(dashboard.LATEST.read_text(encoding="utf-8")) if dashboard.LATEST.exists() else None


# ── 사이드바 ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 단타 트레이딩")
    st.caption(f"프로그램 버전: **{__version__}**")
    st.caption("전략: 과매도 반등형 · 다음날 시가 매수 → 당일 종가 매도")
    market = st.selectbox("스캔 시장", ["ALL", "KOSPI", "KOSDAQ"], format_func=lambda m: {"ALL": "전체", "KOSPI": "코스피", "KOSDAQ": "코스닥"}[m])
    limit = st.select_slider("스캔 종목 수 (거래대금 상위)", options=[100, 200, 300, 500], value=300)
    th = st.slider("추천 기준 점수", 40, 90, int(STRAT.default_threshold), 5)
    st.divider()
    st.caption(f"⚠ {DISCLAIMER}")

tab_today, tab_one, tab_my, tab_perf, tab_help = st.tabs(
    ["📊 오늘의 매매", "🔎 종목 분석", "💼 내 모의매매", "📈 전략 성적", "❓ 사용법"])

# ── 1. 오늘의 매매 ─────────────────────────────────────────────────────────
with tab_today:
    top = st.columns([3, 1])
    top[0].subheader("오늘의 시장 판정과 추천 종목")
    if top[1].button("🔍 지금 스캔하기", type="primary", use_container_width=True):
        bar = st.progress(0.0, text="종목 목록 불러오는 중…")
        results, errors = scan(market, limit, 30, STRAT, th,
                               progress=lambda i, n: bar.progress(i / n, text=f"분석 중… {i}/{n}"))
        bar.empty()
        if results:
            share, panic = market_state(results, th)
            day = max(r.date for r in results)
            final = journal.bar_is_final(day)
            dashboard.save_latest(results, STRAT.name, th, share, panic, final)
            if final:
                journal.record(results, STRAT.name, th, share, panic)
            st.toast(f"스캔 완료: {len(results)}종목", icon="✅")
        else:
            st.error("스캔에 실패했습니다. 인터넷 연결을 확인하고 다시 시도하세요.")

    latest = load_latest()
    if not latest:
        banner("info", "아직 스캔 결과가 없습니다", "오른쪽 위 <b>[지금 스캔하기]</b>를 누르세요. 장 마감 후(16시 이후)에 하는 것이 정확합니다.", "ℹ️")
    else:
        if latest["투매일"]:
            banner("good", "매매일: 시장 전반 투매일",
                   f"신호 비율 {latest['신호비율']:.1f}% (기준 {PANIC_SHARE:g}% 이상). 과거 이런 날 다음날 반등 매매는 평균 +1.85%, 승률 63%. "
                   "하락이 이어지면 크게 잃을 수 있으니 여러 종목에 나눠 소액으로.", "✅")
        else:
            banner("bad", "쉬는 날: 매매 비추천",
                   f"신호 비율 {latest['신호비율']:.1f}% (기준 {PANIC_SHARE:g}% 미만). 소수 종목만 신호가 난 날은 과거 평균이 마이너스였습니다. "
                   "아래 목록은 참고용입니다.", "⛔")
        if not latest["확정"]:
            st.warning("장 마감(15:40) 전 결과입니다. 캔들이 미완성이니 16시 이후 다시 스캔하세요.", icon="⚠️")
        st.caption(f"기준일 {latest['기준일']} · {latest['스캔종목수']}종목 스캔 · {latest['생성']} 업데이트")

        picks = latest["추천"]
        if not picks:
            st.info("기준 점수 이상인 종목이 없습니다.")
        else:
            tbl = pd.DataFrame([{"종목": p["종목"], "코드": p["코드"], "점수": p["점수"], "등락%": p["등락"],
                                 "종가": p["종가"], "손절폭": p["손절폭"], "과거승률%": p["과거승률"],
                                 "과거평균%": p["과거평균"]} for p in picks])
            st.markdown("**추천 종목** — 줄을 클릭하면 차트와 매수 버튼이 나옵니다.")
            ev = st.dataframe(tbl, hide_index=True, use_container_width=True, on_select="rerun",
                              selection_mode="single-row", key="picks",
                              column_config={"점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.0f"),
                                             "등락%": st.column_config.NumberColumn(format="%+.2f"),
                                             "종가": st.column_config.NumberColumn(format="%,.0f"),
                                             "손절폭": st.column_config.NumberColumn(format="%,.0f")})
            rows = ev.selection.rows if ev and ev.selection else []
            p = picks[rows[0]] if rows else picks[0]
            st.plotly_chart(candle_chart(p["코드"], p["종목"]), use_container_width=True)
            st.markdown("**신호:** " + ", ".join(p["신호"]))
            buy_box(p["코드"], p["종목"], latest["기준일"], p["손절폭"] / strategy.STOP_ATR, p["점수"], f"t_{p['코드']}")

# ── 2. 종목 분석 ──────────────────────────────────────────────────────────
with tab_one:
    st.subheader("원하는 종목 분석")
    q = st.text_input("종목명 또는 코드 (쉼표로 여러 개)", placeholder="예: 삼성전자, 에코프로, 005930")
    if q:
        for sym in [s.strip() for s in q.split(",") if s.strip()]:
            try:
                code, name = resolve(sym)
                r = analyze_df(code, name, load_bars(code), STRAT, th)
            except Exception as e:
                st.error(f"{sym}: {e}")
                continue
            with st.container(border=True):
                c = st.columns(5)
                c[0].metric("종목", name)
                c[0].caption(code)
                c[1].metric("종가", f"{r.close:,.0f}", f"{r.chg_pct:+.2f}%", delta_color="inverse")  # 상승 빨강
                c[2].metric("점수", f"{r.score:.0f}")
                c[2].caption(r.grade)
                c[3].metric("RSI(14)", f"{r.rsi:.1f}")
                bt = r.backtest
                c[4].metric("과거 신호 성적", f"{bt['평균수익%']:+.2f}%" if bt.get("거래수") else "–")
                c[4].caption(f"{bt['거래수']}회 · 승률 {bt['승률%']}%" if bt.get("거래수") else "신호 없음")
                st.plotly_chart(candle_chart(code, name), use_container_width=True, key=f"c_{code}")
                st.markdown("**긍정 신호:** " + (", ".join(r.signals_on) or "없음") +
                            "  \n**주의 신호:** " + (", ".join(r.warnings) or "없음"))
                if r.score >= th:
                    buy_box(code, name, r.date, r.plan["손절폭"] / strategy.STOP_ATR, r.score, f"o_{code}")
                else:
                    st.caption(f"기준 점수({th}점) 미만이라 매수 신호가 아닙니다.")

# ── 3. 내 모의매매 ────────────────────────────────────────────────────────
with tab_my:
    h = st.columns([3, 1])
    h[0].subheader("내 모의매매")
    h[1].button("🔄 시세 새로고침", use_container_width=True, key="refresh")
    with st.spinner("시세 확인 중…"):
        book = paper.refresh()
    s = paper.stats(book)
    m = st.columns(4)
    m[0].metric("청산 거래", f"{s['거래수']}건")
    m[1].metric("승률", f"{s['승률%']}%" if s["승률%"] is not None else "–")
    m[2].metric("평균 수익률", f"{s['평균수익%']:+.2f}%" if s["평균수익%"] is not None else "–")
    m[3].metric("누적 손익", f"{s['총손익']:+,}원")

    pend, hold = book[book["상태"] == "예약"], book[book["상태"] == "보유"]
    st.markdown("#### ⏳ 매수 예약 (다음 거래일 시가 체결)")
    if pend.empty:
        st.caption("예약된 주문이 없습니다. '오늘의 매매'나 '종목 분석'에서 모의 매수하세요.")
    for _, r in pend.iterrows():
        c = st.columns([3, 2, 1])
        c[0].write(f"**{r['종목']}** ({r['코드']}) · 신호일 {r['주문일']}")
        c[1].write(f"투자금액 {float(r['투자금액']):,.0f}원")
        if c[2].button("취소", key=f"cx_{r['id']}"):
            paper.cancel(r["id"])
            st.rerun()

    st.markdown("#### 📌 보유 중 (오늘 장 마감 시 자동 매도)")
    if hold.empty:
        st.caption("보유 중인 종목이 없습니다.")
    for _, r in hold.iterrows():
        cur, buy = float(r["현재가"] or r["매수가"]), float(r["매수가"])
        pnl = (cur / buy - 1) * 100
        c = st.columns([3, 2, 2, 2, 1])
        c[0].write(f"**{r['종목']}** ({r['코드']}) · {int(float(r['수량']))}주")
        c[1].metric("매수가", f"{buy:,.0f}")
        c[2].metric("현재가", f"{cur:,.0f}", f"{pnl:+.2f}%", delta_color="inverse")
        c[3].metric("손절가", f"{float(r['손절가']):,.0f}")
        if c[4].button("지금 매도", key=f"sell_{r['id']}", type="primary"):
            price = paper.sell_now(r["id"])
            st.toast(f"{r['종목']} {price:,.0f}원에 모의 매도", icon="💰")
            st.rerun()
    if len(hold):
        st.caption("현재가는 무료 시세라 몇 분 늦을 수 있습니다. 실제 주문은 증권사 앱에서 하세요.")

    st.markdown("#### ✅ 청산 내역")
    done = book[book["상태"] == "청산"].sort_values("매도일", ascending=False)
    if done.empty:
        st.caption("아직 청산된 거래가 없습니다.")
    else:
        st.dataframe(done[["매도일", "종목", "매수가", "매도가", "수량", "청산사유", "수익%", "손익"]],
                     hide_index=True, use_container_width=True,
                     column_config={"수익%": st.column_config.NumberColumn(format="%+.2f"),
                                    "손익": st.column_config.NumberColumn(format="%+,.0f"),
                                    "매수가": st.column_config.NumberColumn(format="%,.0f"),
                                    "매도가": st.column_config.NumberColumn(format="%,.0f")})
        eq = done.sort_values("매도일").groupby("매도일")["손익"].sum().cumsum()
        fig = go.Figure(go.Scatter(x=eq.index, y=eq.values, mode="lines+markers", line=dict(color=SERIES, width=2),
                                   marker=dict(size=8), hovertemplate="%{x}<br>누적 %{y:+,.0f}원<extra></extra>"))
        fig.update_layout(title="누적 손익", height=280, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

# ── 4. 전략 성적 (전진 검증) ───────────────────────────────────────────────
with tab_perf:
    st.subheader("전략 성적 — 매일 기록된 추천의 실제 다음날 결과")
    if st.button("🔄 결과 업데이트", key="track"):
        with st.spinner("다음날 시세 확인 중…"):
            n = journal.update()
        st.toast(f"새 결과 {n}건 반영", icon="✅")
    sm = journal.summary()
    if not sm:
        st.info("아직 기록이 없습니다. 장 마감 후 매일 스캔하면 자동으로 쌓입니다.")
    else:
        c = st.columns(3)
        for col, k, exp in [(c[0], "투매일 신호", "+1.85%"), (c[1], "평상시 신호", "약 0% 이하")]:
            v = sm[k]
            col.metric(k + " 평균", f"{v['평균수익%']:+.2f}%" if v["평균수익%"] is not None else "–")
            col.caption((f"{v['거래수']}건 · 승률 {v['승률%']}%" if v["거래수"] else "아직 없음") + f" · 과거 기대 {exp}")
        c[2].metric("투매일에만 매매 시 누적", f"{sm['투매일만 매매 시 누적%']:+.2f}%" if sm["투매일만 매매 시 누적%"] is not None else "–")
        c[2].caption(f"기록 {sm['기록일수']}일 · 투매일 {sm['투매일수']}일")
        if sm["투매일 신호"]["거래수"] < 30:
            st.warning("투매일 거래가 30건 미만이라 아직 판단하기 이릅니다. 그때까지는 실제 돈 없이 지켜보세요.", icon="⚠️")
        days = journal._read(journal.DAYS)
        if len(days):
            d = days.drop_duplicates("기준일", keep="last").tail(60)
            fig = go.Figure(go.Bar(x=d["기준일"], y=d["신호비율%"], marker_color=SERIES,
                                   hovertemplate="%{x}<br>신호 비율 %{y:.1f}%<extra></extra>"))
            fig.add_hline(y=PANIC_SHARE, line_dash="dash", line_color="#52514e",
                          annotation_text=f"투매일 기준 {PANIC_SHARE:g}%", annotation_position="top right")
            fig.update_layout(title="시장 신호 비율 (막대가 기준선을 넘으면 투매일)", height=300,
                              margin=dict(l=10, r=10, t=40, b=10), yaxis_ticksuffix="%")
            st.plotly_chart(fig, use_container_width=True)
        if sm["최근"] is not None:
            st.dataframe(sm["최근"].iloc[::-1], hide_index=True, use_container_width=True)

# ── 5. 사용법 ─────────────────────────────────────────────────────────────
with tab_help:
    st.markdown(f"""
### 하루 흐름
1. **장 마감 후 (16시 이후)** — `📊 오늘의 매매` 탭에서 **[지금 스캔하기]**
   - ✅ **매매일**이면 추천 종목을 눌러 차트를 보고 **[모의 매수 예약]**
   - ⛔ **쉬는 날**이면 아무것도 하지 않습니다 (대부분의 날)
2. **다음 날 장중** — `💼 내 모의매매` 탭: 시가에 체결된 종목의 현재가·손익 확인, 원하면 **[지금 매도]**
3. **장 마감 후** — 보유 종목은 종가에 자동 매도. `📈 전략 성적` 탭에서 **[결과 업데이트]**

### 규칙
- 매수: 신호 다음 거래일 **시가** · 매도: 같은 날 **종가** (당일 청산) · 손절: 시가 − 1×ATR
- 투매일(스캔 종목 중 {PANIC_SHARE:g}% 이상이 동시에 신호)에만 매매. 1년에 8번 정도뿐입니다.
- 과거 4년 검증: 투매일 평균 +1.85%, 승률 63% / 최악의 날 −11.8%
- **투매일 거래가 30건 이상 쌓일 때까지(몇 달)는 모의매매로만** 확인하세요.

### 참고
- 시세는 무료 데이터(FinanceDataReader)라 장중에는 몇 분 늦을 수 있습니다.
- 이 화면은 모의매매만 합니다. 실제 주문은 증권사 앱에서 직접 하세요.
""")
