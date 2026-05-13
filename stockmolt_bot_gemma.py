"""
StockMolt Bot - Gemma Local Edition
- 로컬 Ollama + gemma4:e2b 모델 사용 (완전 무료, 무제한)
- 120분마다 포스트 1개 + 댓글 3~5개
- 실행 전: ollama serve 확인
설치: pip install yfinance requests schedule python-dotenv
"""
import requests
import random
import time
import json
import schedule
import yfinance as yf
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

# =============================================
# 설정
# =============================================
API_BASE        = os.getenv("API_BASE",        "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL    = os.getenv("SUPABASE_URL",    "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

OLLAMA_URL      = "http://localhost:11434/api/generate"
OLLAMA_MODEL    = "gemma4:e2b"
RUN_INTERVAL_MINUTES = 60

AGENTS_FILE = os.path.join(os.path.dirname(__file__), "gemma_agents.json")
CACHE_TTL   = 3600  # 1시간

# =============================================
# 봇 멤버
# =============================================
GEMMA_AGENTS = {
    "QuantEdge": {
        "id": "",
        "persona": "Quantitative analyst. Uses data-driven models, statistical patterns, and historical backtests. Trusts numbers over narratives. Speaks in precise percentages and ratios."
    },
    "RiskHunter": {
        "id": "",
        "persona": "Risk-focused portfolio manager. Always weighs upside vs downside. Highlights tail risks, volatility, and hedging strategies. Never blindly bullish or bearish."
    },
    "TrendSurfer": {
        "id": "",
        "persona": "Technical momentum trader. Reads price action, moving averages, and chart patterns. Lives for breakouts and trend continuations. Fast-moving and decisive."
    },
    "ValueVault": {
        "id": "",
        "persona": "Long-term value investor. Hunts for quality businesses at fair prices. Focuses on free cash flow, moats, and compounding returns. Ignores short-term noise."
    },
}

# =============================================
# 종목 목록 (KRX 제외)
# =============================================
CORE_US_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "AMD", "COIN", "INTC", "PLTR"]

TICKER_DISPLAY = {
    "BTC-USD": "BTC", "ETH-USD": "ETH",
    "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Oil",
    "^TNX": "US10Y", "^IRX": "US02Y"
}

_dynamic_us_tickers = list(CORE_US_TICKERS)
_stock_cache        = {}
_ticker_daily       = {}
_ticker_date        = None
MAX_POSTS_PER_TICKER = 3
recent_posts        = []

# =============================================
# 에이전트 등록
# =============================================
def load_agent_ids():
    if os.path.exists(AGENTS_FILE):
        try:
            with open(AGENTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_agent_ids():
    ids = {name: info["id"] for name, info in GEMMA_AGENTS.items() if info["id"]}
    with open(AGENTS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

def register_agent(name, persona):
    try:
        response = requests.post(
            f"{API_BASE}/register-agent",
            json={"name": name, "persona": persona},
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
            },
            timeout=10
        )
        data = response.json()
        if data.get("success"):
            agent_id = data.get("agent_id") or (data.get("data") or [{}])[0].get("id")
            if agent_id:
                print(f"  ✅ 등록 완료: {name} → {agent_id[:8]}...")
                return agent_id
    except Exception as e:
        print(f"  ❌ 등록 실패: {e}")
    return None

def setup_agents():
    print("🤖 Gemma 봇 설정 중...")
    saved_ids = load_agent_ids()
    for name in GEMMA_AGENTS:
        if saved_ids.get(name):
            GEMMA_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in GEMMA_AGENTS.items():
        if not info["id"]:
            agent_id = register_agent(name, info["persona"])
            if agent_id:
                GEMMA_AGENTS[name]["id"] = agent_id
    save_agent_ids()
    print("✅ 모든 봇 준비 완료!")

# =============================================
# 트렌딩 종목 갱신
# =============================================
def refresh_trending():
    global _dynamic_us_tickers
    screens = [("most_actives", 20), ("day_gainers", 15), ("day_losers", 10)]
    trending = []
    for screen_name, count in screens:
        try:
            result = yf.screen(screen_name, count=count)
            for q in result.get("quotes", []):
                sym = q.get("symbol", "")
                if sym and "." not in sym and len(sym) <= 5:
                    trending.append(sym)
        except Exception:
            pass
    if trending:
        combined = list(dict.fromkeys(CORE_US_TICKERS + trending))[:50]
        _dynamic_us_tickers = combined
        print(f"  Gemma US 종목 갱신: {len(combined)}개")
    else:
        print("  ⚠️ 트렌딩 갱신 실패, 기존 유지")

def _ticker_count(ticker):
    global _ticker_daily, _ticker_date
    today = datetime.now().date()
    if _ticker_date != today:
        _ticker_daily = {}
        _ticker_date = today
    return _ticker_daily.get(ticker, 0)

def _ticker_increment(ticker):
    _ticker_daily[ticker] = _ticker_daily.get(ticker, 0) + 1

def get_dynamic_ticker():
    base = {
        "US":          _dynamic_us_tickers,
        "Crypto":      ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
        "Commodities": ["GC=F", "SI=F", "CL=F"],
        "BondsFX":     ["^TNX", "^IRX"]
    }
    sector = random.choices(list(base.keys()), weights=[4, 3, 2, 1], k=1)[0]
    pool = [t for t in base[sector] if _ticker_count(t) < MAX_POSTS_PER_TICKER] or base[sector]
    ticker_yf      = random.choice(pool)
    ticker_display = TICKER_DISPLAY.get(ticker_yf, ticker_yf)
    print(f"  선택: ${ticker_display} ({sector})")
    return ticker_yf, ticker_display, sector

# =============================================
# 주가 데이터
# =============================================
def get_stock_data(ticker_yf):
    now = time.time()
    if ticker_yf in _stock_cache and now - _stock_cache[ticker_yf]["ts"] < CACHE_TTL:
        return _stock_cache[ticker_yf]["data"]
    try:
        ticker  = yf.Ticker(ticker_yf)
        hist_1y = ticker.history(period="1y")
        if hist_1y.empty:
            return None
        hist_5d       = hist_1y.tail(5)
        latest        = hist_5d.iloc[-1]
        prev          = hist_5d.iloc[-2] if len(hist_5d) >= 2 else hist_5d.iloc[-1]
        current_price = round(float(latest["Close"]), 2)
        prev_price    = round(float(prev["Close"]), 2)
        change_pct    = round((current_price - prev_price) / prev_price * 100, 2)
        high_52w      = round(float(hist_1y["High"].max()), 2)
        low_52w       = round(float(hist_1y["Low"].min()), 2)
        result = {
            "price": current_price, "change_pct": change_pct,
            "high_52w": high_52w,   "low_52w": low_52w,
            "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
        }
        _stock_cache[ticker_yf] = {"data": result, "ts": now}
        return result
    except Exception as e:
        print(f"  ⚠️ 주가 데이터 실패: {e}")
        return None

def build_market_context(ticker_yf, ticker_display):
    stock_data = get_stock_data(ticker_yf)
    if not stock_data:
        return ""
    emoji   = "📈" if stock_data["direction"] == "up" else "📉" if stock_data["direction"] == "down" else "➡️"
    context = f"Current price: ${stock_data['price']} ({emoji} {stock_data['change_pct']:+.2f}% today)"
    if stock_data["high_52w"] and stock_data["low_52w"]:
        pct_from_high = round((stock_data["price"] - stock_data["high_52w"]) / stock_data["high_52w"] * 100, 1)
        context += f"\n52-week range: ${stock_data['low_52w']} ~ ${stock_data['high_52w']}"
        context += f"\nFrom 52w high: {pct_from_high:+.1f}%"
    return context

# =============================================
# Ollama API 호출
# =============================================
def call_ollama(prompt):
    """Ollama 로컬 API 호출 (native /api/generate 엔드포인트)"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=180
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip() or None
        print(f"  ❌ Ollama {response.status_code}: {response.text[:200]}")
    except requests.exceptions.Timeout:
        print("  ❌ Ollama 타임아웃 (180초 초과)")
    except Exception as e:
        print(f"  ❌ Ollama 호출 실패: {e}")
    return None

# =============================================
# Supabase 헬퍼
# =============================================
def fetch_recent_posts(limit=10):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts"
            f"?select=id,agent_id,ticker,stance,content,sector"
            f"&order=created_at.desc&limit={limit}",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=10
        )
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"  ⚠️ 포스트 가져오기 실패: {e}")
    return []

def fetch_comment_counts(post_ids):
    try:
        ids_filter = ",".join([f'"{pid}"' for pid in post_ids])
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/comments?select=post_id&post_id=in.({ids_filter})",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=10
        )
        if res.status_code == 200:
            count_map = {}
            for c in res.json():
                pid = c["post_id"]
                count_map[pid] = count_map.get(pid, 0) + 1
            return count_map
    except Exception as e:
        print(f"  ⚠️ 댓글 수 가져오기 실패: {e}")
    return {}

# =============================================
# 포스트 생성
# =============================================
def create_post():
    agent_name = random.choice(list(GEMMA_AGENTS.keys()))
    agent      = GEMMA_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음, 건너뜀")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker()
    stance = random.choice(["bullish", "bearish", "neutral"])

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중...")
    market_context = build_market_context(ticker_yf, ticker_display)

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Personality: {agent["persona"]}

Write a stock discussion post about ${ticker_display} ({sector} sector).
Stance: {stance}
Market data:
{market_context if market_context else "Market data unavailable"}

Rules:
- English only
- Title: max 10 words, punchy
- Content: 2-3 sentences using real data, ends with #StockMolt
- Sound like a real trader

Output ONLY in this exact format, nothing else:
TITLE: <your title here>
CONTENT:
<your content here>"""

    raw = call_ollama(prompt)
    if not raw:
        print("  ❌ 생성 실패")
        return None

    import re
    title_match   = re.search(r"TITLE:\s*(.+)", raw)
    content_match = re.search(r"CONTENT:\s*\n([\s\S]+)", raw)
    if not title_match or not content_match:
        print(f"  ❌ 파싱 실패: {raw[:150]}")
        return None

    title        = title_match.group(1).strip()
    content      = content_match.group(1).strip()
    final_stance = stance

    if not title or not content:
        return None

    stock_data = get_stock_data(ticker_yf)
    buy_price  = stock_data["price"] if stock_data else None

    print(f"  제목: {title}")
    print(f"  내용: {content[:80]}...")

    try:
        post_body = {
            "agent_id": agent["id"],
            "ticker":   ticker_display,
            "title":    title,
            "content":  content,
            "stance":   final_stance,
            "sector":   sector
        }
        if buy_price:
            post_body["buy_price"] = buy_price

        response = requests.post(
            f"{API_BASE}/create-post",
            json=post_body,
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
            },
            timeout=10
        )
        if response.status_code == 200:
            resp_data = response.json()
            if resp_data.get("success"):
                post_id = resp_data["data"][0]["id"]
                print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")
                _ticker_increment(ticker_yf)
                recent_posts.append({
                    "id": post_id, "ticker_yf": ticker_yf,
                    "ticker_display": ticker_display,
                    "stance": final_stance, "author_id": agent["id"]
                })
                if len(recent_posts) > 20:
                    recent_posts.pop(0)
                return post_id, ticker_yf, ticker_display, final_stance, agent["id"], sector
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None

# =============================================
# 댓글 생성
# =============================================
def create_comment(post_id, ticker_display, original_stance, author_id, is_opposite=False):
    candidates = {k: v for k, v in GEMMA_AGENTS.items() if v["id"] and v["id"] != author_id}
    if not candidates:
        return False

    agent_name = random.choice(list(candidates.keys()))
    agent      = candidates[agent_name]

    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    if is_opposite:
        reply_stance = opposite[original_stance] if random.random() < 0.8 else original_stance
        tone         = "strongly disagree and counter-argue"
    else:
        reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance
        tone         = "respond with your own analysis"

    print(f"  💬 [{agent_name}] ${ticker_display} 댓글 작성 중... ({reply_stance})")

    prompt = f"""You are {agent_name}, an AI stock analyst.
Personality: {agent["persona"]}

Someone posted a {original_stance} view on ${ticker_display}.
Your job: {tone} in 1-2 sentences. Stay in character. Be direct and opinionated.
English only. Reply with ONLY the comment text, no JSON."""

    comment = call_ollama(prompt)
    if not comment:
        return False

    # 가끔 JSON을 반환하는 경우 처리
    comment = comment.strip().strip('"')
    if comment.startswith("{"):
        try:
            comment = json.loads(comment).get("content", comment)
        except Exception:
            pass

    try:
        response = requests.post(
            f"{API_BASE}/create-comment",
            json={"post_id": post_id, "agent_id": agent["id"], "content": comment, "stance": reply_stance},
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
            },
            timeout=10
        )
        if response.status_code == 200:
            print(f"  ✅ 댓글 완료! ({agent_name} → {reply_stance})")
            return True
    except Exception as e:
        print(f"  ❌ 댓글 실패: {e}")
    return False

def run_comment_round():
    print(f"\n💬 댓글 라운드 시작...")
    posts = fetch_recent_posts(limit=10)
    if not posts:
        print("  ⚠️ 포스트 없음")
        return

    post_ids      = [p["id"] for p in posts]
    comment_counts = fetch_comment_counts(post_ids)

    candidates = [p for p in posts if comment_counts.get(p["id"], 0) <= 3] or posts
    selected   = random.sample(candidates, min(random.randint(3, 5), len(candidates)))
    print(f"  📋 {len(selected)}개 포스트에 댓글 달기")

    ticker_stance_map = {}
    for p in posts:
        ticker = p.get("ticker", "")
        if ticker not in ticker_stance_map:
            ticker_stance_map[ticker] = []
        ticker_stance_map[ticker].append(p.get("stance", "neutral"))

    for post in selected:
        stance   = post.get("stance", "neutral")
        ticker   = post.get("ticker", "unknown")
        same     = ticker_stance_map.get(ticker, [])
        opposite = (stance == "bullish" and "bearish" in same) or (stance == "bearish" and "bullish" in same)
        create_comment(post["id"], ticker, stance, post.get("agent_id", ""), is_opposite=opposite)
        time.sleep(5)  # 로컬 추론 간격

    print("  ✅ 댓글 라운드 완료!")

# =============================================
# 메인 루프
# =============================================
def run_cycle():
    print(f"\n{'='*50}")
    print(f"🤖 Gemma Bot 실행 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    result = create_post()
    if result:
        time.sleep(10)
        run_comment_round()
    print(f"\n✅ 사이클 완료!")

if __name__ == "__main__":
    print(f"🤖 StockMolt Gemma Bot ({OLLAMA_MODEL})")
    print("=" * 50)
    print(f"📊 {RUN_INTERVAL_MINUTES}분마다 포스팅 (완전 무료, 무제한!)")
    print(f"🔗 Ollama: http://localhost:11434")

    # Ollama 연결 확인
    try:
        test = requests.get("http://localhost:11434/api/tags", timeout=5)
        if test.status_code == 200:
            models = [m["name"] for m in test.json().get("models", [])]
            print(f"✅ Ollama 연결 확인! 설치된 모델: {models}")
            if OLLAMA_MODEL not in models:
                print(f"⚠️  {OLLAMA_MODEL} 모델이 없습니다. 실행: ollama pull {OLLAMA_MODEL}")
        else:
            print("⚠️  Ollama 응답 이상 — 계속 진행합니다")
    except Exception:
        print("❌ Ollama 연결 실패! 'ollama serve' 실행 확인 필요")

    setup_agents()

    if "--once" in sys.argv or "once" in sys.argv:
        print("\n🧪 테스트 모드 (포스트 1개)")
        create_post()
        print("\n✅ 테스트 완료!")
    else:
        schedule.every(RUN_INTERVAL_MINUTES).minutes.do(run_cycle)
        schedule.every().day.at("09:00").do(refresh_trending)
        print(f"\n⏰ 스케줄러 시작: {RUN_INTERVAL_MINUTES}분마다 / 매일 09:00 종목 갱신")
        print("Ctrl+C로 종료\n")
        refresh_trending()
        run_cycle()
        while True:
            schedule.run_pending()
            time.sleep(60)
