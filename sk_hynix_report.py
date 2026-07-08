"""SK 하이닉스 투자 레포트 생성기

네이버 뉴스 + Yahoo Finance 주가 데이터를 결합해
기술 분석 기반 매수/매도 추천 HTML 레포트를 생성한다.

사용법:
    python sk_hynix_report.py              # 기본: 최근 3개월
    python sk_hynix_report.py --months 6   # 6개월 데이터

준비:
    네이버 API 키 필요 (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET)
    - naver_news_sk_hynix.py 참고
    - yfinance 는 자동 설치됨 (pip install yfinance)
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import datetime
import argparse
import base64


# ===== 설정 =====
TICKER = "000660.KS"          # SK 하이닉스 (Yahoo Finance 심볼)
QUERY = "SK 하이닉스"
NEWS_COUNT = 5

# .env 로드 (네이버 키)
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value

load_env_file()
CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")


def clean_text(s):
    return (
        s.replace("&quot;", '"').replace("&#39;", "'")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    )


# ===== 네이버 뉴스 =====
def fetch_news():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[경고] 네이버 API 키 없음 - 뉴스 섹션 생략")
        return []
    url = "https://openapi.naver.com/v1/search/news.json"
    params = urllib.parse.urlencode(
        {"query": QUERY, "display": NEWS_COUNT, "start": 1, "sort": "date"}
    )
    req = urllib.request.Request(f"{url}?{params}")
    req.add_header("X-Naver-Client-Id", CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", CLIENT_SECRET)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[뉴스 오류] {e}")
        return []
    return [
        {
            "title": clean_text(it.get("title", "")),
            "link": it.get("link", ""),
            "pubDate": it.get("pubDate", ""),
            "desc": clean_text(it.get("description", "")),
        }
        for it in data.get("items", [])
    ]


# ===== 주가 데이터 (Yahoo Finance 직접 API 호출) =====
def fetch_stock(months):
    """Yahoo Finance의 chart API를 직접 호출해 일별 OHLCV 데이터를 가져온다.
    yfinance 의존성/SSL 인증서 문제를 우회하기 위해 urllib 사용."""
    import ssl
    end = int(datetime.datetime.now().timestamp())
    start = int((datetime.datetime.now() - datetime.timedelta(days=months * 30 + 5)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"
           f"?period1={start}&period2={end}&interval=1d")
    # SSL 검증 비활성화 (회사 방화벽 환경 대응)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Yahoo Finance 요청 실패: HTTP {e.code}")
    except Exception as e:
        raise RuntimeError(f"주가 데이터 조회 오류: {e}")

    result = data.get("chart", {}).get("result")
    if not result:
        raise RuntimeError("주가 데이터를 가져오지 못했습니다 (티커/네트워크 확인)")
    ts = result[0]["timestamp"]
    quote = result[0]["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        d = datetime.datetime.utcfromtimestamp(t).date()
        rows.append({
            "Date": d,
            "Open": quote["open"][i],
            "High": quote["high"][i],
            "Low": quote["low"][i],
            "Close": quote["close"][i],
            "Volume": quote["volume"][i],
        })
    df = pd.DataFrame(rows).set_index("Date")
    df = df.dropna(subset=["Close"])
    return df


import pandas as pd  # noqa: E402




# ===== 기술 분석 =====
def analyze(df):
    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)

    # 이동평균선
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    # RSI (14일)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # 최근 가격
    cur = float(close.iloc[-1])
    cur_ma20 = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None
    cur_ma60 = float(ma60.iloc[-1]) if not pd.isna(ma60.iloc[-1]) else None
    cur_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None

    # 기간 내 최고/최저
    hi = float(close.max())
    lo = float(close.min())
    pos = (cur - lo) / (hi - lo) * 100 if hi > lo else 50

    return {
        "df": df, "close": close, "volume": volume,
        "ma20": ma20, "ma60": ma60, "rsi": rsi,
        "cur": cur, "cur_ma20": cur_ma20, "cur_ma60": cur_ma60, "cur_rsi": cur_rsi,
        "hi": hi, "lo": lo, "pos": pos,
    }


def signal(a):
    """규칙 기반 매수/매도 신호. +1 매수, -1 매도 가중."""
    score = 0
    reasons = []

    # 1) 골든/데드 크로스
    if a["cur_ma20"] and a["cur_ma60"]:
        if a["cur_ma20"] > a["cur_ma60"]:
            score += 1
            reasons.append("단기이평선이 장기이평선 위(골든크로스) - 상승 추세")
        else:
            score -= 1
            reasons.append("단기이평선이 장기이평선 아래(데드크로스) - 하락 추세")

    # 2) 현재가 vs MA20
    if a["cur_ma20"]:
        if a["cur"] > a["cur_ma20"]:
            score += 1
            reasons.append(f"현재가 {a['cur']:.0f}원이 MA20 {a['cur_ma20']:.0f}원 위 - 단기 강세")
        else:
            score -= 1
            reasons.append(f"현재가 {a['cur']:.0f}원이 MA20 {a['cur_ma20']:.0f}원 아래 - 단기 약세")

    # 3) RSI
    if a["cur_rsi"] is not None:
        if a["cur_rsi"] < 30:
            score += 2
            reasons.append(f"RSI {a['cur_rsi']:.1f} - 과매도 구간 (반등 가능)")
        elif a["cur_rsi"] > 70:
            score -= 2
            reasons.append(f"RSI {a['cur_rsi']:.1f} - 과매수 구간 (조정 가능)")
        else:
            reasons.append(f"RSI {a['cur_rsi']:.1f} - 중립 구간")

    # 4) 기간 내 위치
    if a["pos"] > 80:
        score -= 1
        reasons.append(f"최근 최고가 대비 {a['pos']:.0f}% 위치 - 고점 근접")
    elif a["pos"] < 20:
        score += 1
        reasons.append(f"최근 최저가 대비 {a['pos']:.0f}% 위치 - 저점 근접")

    if score >= 2:
        action = "BUY"
        label = "매수 추천"
    elif score <= -2:
        action = "SELL"
        label = "매도 추천"
    else:
        action = "HOLD"
        label = "관망 (보유 유지)"

    return {"action": action, "label": label, "score": score, "reasons": reasons}


# ===== HTML 렌더링 =====
def render_html(news, a, sig, months):
    # 차트용 데이터
    dates = [d.strftime("%Y-%m-%d") for d in a["close"].index]
    closes = [round(float(v), 0) for v in a["close"].values]
    ma20 = [None if pd.isna(v) else round(float(v), 0) for v in a["ma20"].values]
    ma60 = [None if pd.isna(v) else round(float(v), 0) for v in a["ma60"].values]
    volumes = [int(v) for v in a["volume"].values]

    # 색상
    color_map = {"BUY": "#27ae60", "SELL": "#e74c3c", "HOLD": "#f39c12"}
    action_color = color_map[sig["action"]]

    news_cards = ""
    if news:
        for i, n in enumerate(news, 1):
            news_cards += f"""
        <div class="news-card">
          <div class="news-num">{i}</div>
          <div>
            <div class="news-title">{n['title']}</div>
            <div class="news-meta">{n['pubDate']}</div>
            <div class="news-desc">{n['desc']}</div>
            <a class="news-link" href="{n['link']}" target="_blank">기사 전문 보기 →</a>
          </div>
        </div>"""
    else:
        news_cards = '<div class="empty">뉴스를 불러오지 못했습니다 (네이버 API 키 필요).</div>'

    reasons_html = "".join(f'<li>{r}</li>' for r in sig["reasons"])

    today = datetime.date.today().strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SK하이닉스 투자 레포트</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,"Segoe UI",Roboto,"Malgun Gothic",sans-serif;
         background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);
         color:#e2e8f0; padding:24px; min-height:100vh; }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  header {{ text-align:center; margin-bottom:30px; }}
  header h1 {{ font-size:1.8rem; margin-bottom:6px; }}
  header .sub {{ color:#94a3b8; font-size:0.95rem; }}
  .action-box {{ text-align:center; background:{action_color}; color:white;
    border-radius:18px; padding:28px; margin-bottom:24px; box-shadow:0 10px 40px rgba(0,0,0,0.3); }}
  .action-box .label {{ font-size:1.1rem; opacity:0.9; }}
  .action-box .action {{ font-size:3rem; font-weight:800; margin:8px 0; }}
  .action-box .score {{ font-size:0.95rem; opacity:0.9; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:24px; }}
  @media (max-width:700px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  .card {{ background:#1e293b; border-radius:14px; padding:20px; }}
  .card h3 {{ color:#94a3b8; font-size:0.9rem; text-transform:uppercase; margin-bottom:14px; }}
  .price {{ font-size:2.4rem; font-weight:700; color:#38bdf8; }}
  .stat {{ display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #334155; font-size:0.93rem; }}
  .stat:last-child {{ border:0; }}
  .stat .v {{ font-weight:600; color:#f1f5f9; }}
  .pos {{ margin-top:10px; height:8px; background:#334155; border-radius:4px; overflow:hidden; }}
  .pos div {{ height:100%; background:linear-gradient(90deg,#10b981,#f59e0b,#ef4444);
    width:{a['pos']:.0f}%; border-radius:4px; }}
  .chart-card {{ background:#1e293b; border-radius:14px; padding:20px; margin-bottom:24px; }}
  .chart-card h3 {{ color:#94a3b8; font-size:0.9rem; text-transform:uppercase; margin-bottom:14px; }}
  canvas {{ max-height:360px; }}
  .news-list {{ display:flex; flex-direction:column; gap:12px; }}
  .news-card {{ display:flex; gap:14px; background:#1e293b; border-radius:12px; padding:16px; }}
  .news-num {{ background:#3b82f6; color:white; width:28px; height:28px; border-radius:50%;
    display:flex; align-items:center; justify-content:center; font-weight:700; flex-shrink:0; }}
  .news-title {{ font-weight:600; font-size:1rem; margin-bottom:4px; }}
  .news-meta {{ color:#64748b; font-size:0.82rem; margin-bottom:8px; }}
  .news-desc {{ color:#cbd5e1; font-size:0.9rem; line-height:1.5; }}
  .news-link {{ color:#3b82f6; font-size:0.85rem; text-decoration:none; }}
  .news-link:hover {{ text-decoration:underline; }}
  .reasons {{ background:#1e293b; border-radius:12px; padding:18px; margin-top:18px; }}
  .reasons h3 {{ color:#94a3b8; font-size:0.9rem; margin-bottom:10px; }}
  .reasons ul {{ padding-left:20px; }}
  .reasons li {{ margin:6px 0; color:#cbd5e1; font-size:0.92rem; }}
  .empty {{ color:#64748b; text-align:center; padding:30px; }}
  footer {{ text-align:center; color:#475569; font-size:0.8rem; margin-top:30px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>SK하이닉스(066570) 투자 레포트</h1>
    <div class="sub">기준일 {today} · 최근 {months}개월 데이터 · 기술 분석 기반</div>
  </header>

  <div class="action-box">
    <div class="label">종합 추천</div>
    <div class="action">{sig['label']}</div>
    <div class="score">신호 점수: {sig['score']:+d} (BUY≥2 / SELL≤-2 / HOLD 그 외)</div>
  </div>

  <div class="grid2">
    <div class="card">
      <h3>현재 주가</h3>
      <div class="price">{a['cur']:,.0f} 원</div>
      <div class="stat"><span>기간 최고</span><span class="v">{a['hi']:,.0f} 원</span></div>
      <div class="stat"><span>기간 최저</span><span class="v">{a['lo']:,.0f} 원</span></div>
      <div class="stat"><span>현재 위치</span><span class="v">{a['pos']:.0f}%</span></div>
      <div class="pos"><div></div></div>
    </div>
    <div class="card">
      <h3>기술 지표</h3>
      <div class="stat"><span>MA20 (20일 이평선)</span><span class="v">{a['cur_ma20']:,.0f} 원</span></div>
      <div class="stat"><span>MA60 (60일 이평선)</span><span class="v">{a['cur_ma60']:,.0f} 원</span></div>
      <div class="stat"><span>RSI (14일)</span><span class="v">{a['cur_rsi']:.1f}</span></div>
      <div class="reasons">
        <h3>판단 근거</h3>
        <ul>{reasons_html}</ul>
      </div>
    </div>
  </div>

  <div class="chart-card">
    <h3>주가 차트 (종가 + 이동평균선)</h3>
    <canvas id="priceChart"></canvas>
  </div>

  <div class="chart-card">
    <h3>거래량</h3>
    <canvas id="volChart"></canvas>
  </div>

  <h3 style="color:#94a3b8;font-size:0.9rem;text-transform:uppercase;margin:24px 0 12px;">최신 뉴스 Top {len(news)}</h3>
  <div class="news-list">{news_cards}</div>

  <footer>
    ⚠️ 본 레포트는 자동 생성된 참고용 자료이며, 실제 투자는 본인 판단으로 결정하세요.
    데이터: Yahoo Finance · 네이버 뉴스
  </footer>
</div>

<script>
const dates = {json.dumps(dates)};
const closes = {json.dumps(closes)};
const ma20 = {json.dumps(ma20)};
const ma60 = {json.dumps(ma60)};
const volumes = {json.dumps(volumes)};

new Chart(document.getElementById('priceChart'), {{
  type:'line',
  data:{{ labels:dates, datasets:[
    {{ label:'종가', data:closes, borderColor:'#38bdf8', borderWidth:2, tension:0.3, pointRadius:0 }},
    {{ label:'MA20', data:ma20, borderColor:'#f59e0b', borderWidth:1.5, tension:0.3, pointRadius:0, borderDash:[5,5] }},
    {{ label:'MA60', data:ma60, borderColor:'#a78bfa', borderWidth:1.5, tension:0.3, pointRadius:0, borderDash:[5,5] }}
  ]}},
  options:{{ responsive:true, plugins:{{ legend:{{ labels:{{ color:'#94a3b8' }} }} }},
    scales:{{ x:{{ ticks:{{ color:'#64748b', maxTicksLimit:8 }} }},
             y:{{ ticks:{{ color:'#64748b' }} }} }} }}
}});

new Chart(document.getElementById('volChart'), {{
  type:'bar',
  data:{{ labels:dates, datasets:[{{ label:'거래량', data:volumes, backgroundColor:'#3b82f680' }}] }},
  options:{{ responsive:true, plugins:{{ legend:{{ display:false }} }},
    scales:{{ x:{{ ticks:{{ color:'#64748b', maxTicksLimit:8 }} }},
             y:{{ ticks:{{ color:'#64748b' }} }} }} }}
}});
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="SK하이닉스 투자 레포트 생성")
    parser.add_argument("--months", type=int, default=3, help="분석 기간 (개월, 기본 3)")
    args = parser.parse_args()

    print(f"[1/4] 네이버 뉴스 검색: {QUERY}")
    news = fetch_news()
    print(f"  → {len(news)}건")

    print(f"[2/4] Yahoo Finance 주가 데이터: {TICKER} (최근 {args.months}개월)")
    df = fetch_stock(args.months)
    print(f"  → {len(df)}일 데이터")

    print("[3/4] 기술 분석 계산")
    a = analyze(df)
    sig = signal(a)
    print(f"  → 추천: {sig['label']} (점수 {sig['score']:+d})")

    print("[4/4] HTML 레포트 생성")
    html = render_html(news, a, sig, args.months)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → {out_path}")

    # 요약 출력
    print("\n" + "=" * 50)
    print(f"추천: {sig['label']}  (점수 {sig['score']:+d})")
    print(f"현재가: {a['cur']:,.0f}원  RSI: {a['cur_rsi']:.1f}")
    print("=" * 50)
    print(f"\n레포트 파일: {out_path}")


if __name__ == "__main__":
    main()
