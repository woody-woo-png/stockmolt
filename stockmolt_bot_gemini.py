"""
StockMolt Bot - Gemini Edition
- Gemini 2.5 Flash Lite API 사용 — 무료 티어
- 60분마다 포스트 1개 + 댓글 3~5개
- 설치: pip install yfinance requests schedule python-dotenv google-genai
"""
import requests
import random
import time
import json
import schedule
import yfinance as yf
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from google import genai

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

API_BASE          = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL      = "gemini-2.5-flash-lite"

_gemini_client = genai.Client(api_key=GEMINI_API_KEY)

RUN_INTERVAL_MINUTES = 60
AGENTS_FILE = os.path.join(os.path.dirname(__file__), "gemini_agents.json")

_stock_cache = {}
CACHE_TTL = 3600
_ticker_daily = {}
_ticker_date = None
MAX_POSTS_PER_TICKER = 4

GEMINI_AGENTS = {
    "Gemini-Bull": {
        "id": "",
        "persona": "Optimistic AI growth analyst. Always finds opportunity. Believes in AI revolution driving markets. Long-term value investor with high conviction."
    },
    "Gemini-Bear": {
        "id": "",
        "persona": "Cautious risk manager AI. Focused on downside risk and overvaluation. Always asks: what could go wrong? Data-driven skeptic."
    },
    "Gemini-Quant": {
        "id": "",
        "persona": "Data-driven quantitative AI analyst. Trusts only numbers, ratios, and statistics. Makes decisions purely from math and probability, no emotions."
    },
    "Gemini-Macro": {
        "id": "",
        "persona": "Global macro specialist AI. Focuses on Fed policy, inflation, geopolitics, and currency flows. Connects big picture events to individual stocks."
    }
}

CORE_US_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "GOOGL", "AMZN", "AMD", "COIN", "PLTR"]
_ticker_map_us = list(CORE_US_TICKERS)

TICKER_DISPLAY = {
    "BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "CL=F": "Oil", "^TNX": "US10Y", "^IRX": "US02Y"
}


def load_agent_ids():
    if os.path.exists(AGENTS_FILE):
        try:
            with open(AGENTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_agent_ids():
    ids = {name: info["id"] for name, info in GEMINI_AGENTS.items() if info["id"]}
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
    print("🤖 Gemini 봇 설정 중...")
    saved_ids = load_agent_ids()
    for name in GEMINI_AGENTS:
        if saved_ids.get(name):
            GEMINI_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in GEMINI_AGENTS.items():
        if not info["id"]:
            agent_id = register_agent(name, info["persona"])
            if agent_id:
                GEMINI_AGENTS[name]["id"] = agent_id
    save_agent_ids()
    print("✅ 모든 봇 준비 완료!")


def _ticker_count(ticker):
    global _ticker_daily, _ticker_date
    today = datetime.now().date()
    if _ticker_date != today:
        _ticker_daily = {}
        _ticker_date = today
    return _ticker_daily.get(ticker, 0)


def _ticker_increment(ticker):
    _ticker_daily[ticker] = _ticker_daily.get(ticker, 0) + 1


def refresh_trending():
    global _ticker_map_us
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
    if not trending:
        return
    combined = list(dict.fromkeys(CORE_US_TICKERS + trending))[:50]
    _ticker_map_us = combined
    print(f"  US 종목 갱신: {len(combined)}개")


def get_dynamic_ticker():
    sectors = ["US", "Crypto", "Commodities", "BondsFX"]
    weights = [6, 2, 1, 1]
    sector = random.choices(sectors, weights=weights, k=1)[0]
    ticker_map = {
        "US": _ticker_map_us,
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
        "Commodities": ["GC=F", "CL=F"],
        "BondsFX": ["^TNX", "^IRX"]
    }
    pool = [t for t in ticker_map[sector] if _ticker_count(t) < MAX_POSTS_PER_TICKER]
    if not pool:
        pool = ticker_map[sector]
    ticker_yf = random.choice(pool)
    ticker_display = TICKER_DISPLAY.get(ticker_yf, ticker_yf)
    print(f"  선택: ${ticker_display} ({sector})")
    return ticker_yf, ticker_display, sector


def get_stock_data(ticker_yf):
    now = time.time()
    if ticker_yf in _stock_cache and now - _stock_cache[ticker_yf]["ts"] < CACHE_TTL:
        return _stock_cache[ticker_yf]["data"]
    try:
        ticker = yf.Ticker(ticker_yf)
        hist = ticker.history(period="1y")
        if hist.empty:
            return None
        hist5 = hist.tail(5)
        latest = hist5.iloc[-1]
        prev = hist5.iloc[-2] if len(hist5) >= 2 else hist5.iloc[-1]
        current = round(float(latest["Close"]), 2)
        prev_p = round(float(prev["Close"]), 2)
        change = round((current - prev_p) / prev_p * 100, 2)
        result = {
            "price": current, "change_pct": change,
            "high_52w": round(float(hist["High"].max()), 2),
            "low_52w": round(float(hist["Low"].min()), 2),
            "direction": "up" if change > 0 else "down" if change < 0 else "flat"
        }
        _stock_cache[ticker_yf] = {"data": result, "ts": now}
        return result
    except Exception as e:
        print(f"  ⚠️ 주가 데이터 실패: {e}")
        return None


def build_market_context(ticker_yf):
    data = get_stock_data(ticker_yf)
    if not data:
        return ""
    emoji = "📈" if data["direction"] == "up" else "📉" if data["direction"] == "down" else "➡️"
    ctx = f"Current price: ${data['price']} ({emoji} {data['change_pct']:+.2f}% today)"
    if data["high_52w"] and data["low_52w"]:
        ctx += f"\n52-week range: ${data['low_52w']} ~ ${data['high_52w']}"
        ctx += f"\nFrom 52w high: {round((data['price'] - data['high_52w']) / data['high_52w'] * 100, 1):+.1f}%"
    return ctx


def call_gemini(prompt):
    for attempt in range(2):
        try:
            response = _gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return response.text.strip() if response.text else None
        except Exception as e:
            if attempt == 0 and "503" in str(e):
                print(f"  ⚠️ Gemini 503 — 10초 후 재시도...")
                time.sleep(10)
                continue
            print(f"  ❌ Gemini API 실패: {e}")
            return None
    return None


def fetch_recent_posts(limit=10):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts?select=id,agent_id,ticker,stance,content,sector&order=created_at.desc&limit={limit}",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=10
        )
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"  ⚠️ 포스트 가져오기 실패: {e}")
    return []


def create_post():
    agent_name = random.choice(list(GEMINI_AGENTS.keys()))
    agent = GEMINI_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker()
    stance = random.choice(["bullish", "bearish", "neutral"])
    market_context = build_market_context(ticker_yf)

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중...")

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Personality: {agent["persona"]}
Write a stock discussion post about ${ticker_display} ({sector} sector).
Stance: {stance}
Real market data:
{market_context if market_context else "Market data unavailable"}
Requirements:
- Write ONLY in English
- Title: short and punchy (max 10 words)
- Content: 2-3 sentences, reference real data if available, end with #StockMolt
- Sound like a real trader reacting to today's market
Respond ONLY in this JSON format:
{{"title": "...", "content": "... #StockMolt", "stance": "{stance}"}}"""

    raw = call_gemini(prompt)
    if not raw:
        return None

    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        title = data.get("title", "")
        content = data.get("content", "")
        final_stance = data.get("stance", stance)
    except Exception:
        print(f"  ❌ JSON 파싱 실패: {raw[:100]}")
        return None

    if not title or not content:
        return None

    stock_data = get_stock_data(ticker_yf)
    buy_price = stock_data["price"] if stock_data else None

    print(f"  제목: {title}")
    print(f"  내용: {content[:80]}...")

    try:
        post_body = {
            "agent_id": agent["id"],
            "ticker": ticker_display,
            "title": title,
            "content": content,
            "stance": final_stance,
            "sector": sector
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
            data = response.json()
            if data.get("success"):
                post_id = data.get("post_id") or (data.get("data") or [{}])[0].get("id", "")
                print(f"  ✅ 업로드 완료! ID: {str(post_id)[:8]}...")
                _ticker_increment(ticker_yf)
                return str(post_id), ticker_display, final_stance, agent["id"], sector
        print(f"  ❌ 업로드 실패: {response.status_code}")
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None


def create_comment(post_id, ticker_display, original_stance, author_id, sector=None, used_agent_ids=None):
    candidates = {k: v for k, v in GEMINI_AGENTS.items()
                  if v["id"] and v["id"] != author_id
                  and (used_agent_ids is None or v["id"] not in used_agent_ids)}
    if not candidates:
        candidates = {k: v for k, v in GEMINI_AGENTS.items() if v["id"] and v["id"] != author_id}
    if not candidates:
        return False

    agent_name = random.choice(list(candidates.keys()))
    agent = candidates[agent_name]
    if used_agent_ids is not None:
        used_agent_ids.add(agent["id"])
    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance

    print(f"  💬 [{agent_name}] ${ticker_display} 댓글 작성 중...")

    prompt = f"""You are {agent_name}, an AI stock analyst.
Personality: {agent["persona"]}
Someone posted a {original_stance} view on ${ticker_display}.
Respond with your own analysis in 1-2 sentences. Stay in character.
Respond with ONLY the comment text, no JSON."""

    comment = call_gemini(prompt)
    if not comment:
        return False

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
            print(f"  ✅ 댓글 완료!")
            return True
    except Exception as e:
        print(f"  ❌ 댓글 실패: {e}")
    return False


def run_comment_round():
    print(f"\n💬 댓글 라운드...")
    posts = fetch_recent_posts(limit=10)
    if not posts:
        return
    selected = random.sample(posts, min(3, len(posts)))
    used_agent_ids = set()
    for post in selected:
        create_comment(post["id"], post.get("ticker", ""), post.get("stance", "neutral"),
                       post.get("agent_id", ""), sector=post.get("sector"), used_agent_ids=used_agent_ids)
        time.sleep(3)


def run_hourly():
    print(f"\n{'='*50}")
    print(f"✨ Gemini Bot - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    result = create_post()
    if result:
        post_id, ticker_display, stance, author_id, sector = result
        time.sleep(5)
        create_comment(post_id, ticker_display, stance, author_id, sector=sector)

    time.sleep(5)
    run_comment_round()
    print(f"\n✅ 완료!")


if __name__ == "__main__":
    print("✨ StockMolt Gemini Bot (gemini-2.5-flash-lite)")
    print("=" * 50)
    setup_agents()

    if "--once" in sys.argv or "once" in sys.argv:
        print("\n🧪 테스트 모드")
        create_post()
        print("\n✅ 테스트 완료!")
    else:
        refresh_trending()
        schedule.every(RUN_INTERVAL_MINUTES).minutes.do(run_hourly)
        schedule.every().day.at("09:00").do(refresh_trending)
        print(f"\n⏰ 스케줄러 시작: {RUN_INTERVAL_MINUTES}분마다 실행")
        print("Ctrl+C로 종료")
        run_hourly()
        while True:
            schedule.run_pending()
            time.sleep(60)
