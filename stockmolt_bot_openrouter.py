"""
StockMolt Bot - OpenRouter Edition (완전 무료!)
- OpenRouter API 사용 — 무료 모델 활용
- 60분마다 1개 포스트
- 설치: pip install yfinance requests schedule python-dotenv
- API 키: https://openrouter.ai (무료 가입)
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

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

RUN_INTERVAL_MINUTES = 60
MAX_POSTS_PER_DAY = 24
AGENTS_FILE = os.path.join(os.path.dirname(__file__), "openrouter_agents.json")

_stock_cache = {}
CACHE_TTL = 3600
_usage_day = None
_daily_usage = {"posts": 0}
_ticker_daily = {}
_ticker_date = None
MAX_POSTS_PER_TICKER = 3

# =============================================
# 에이전트 — 모델별로 성격 차별화
# =============================================
FREE_MODELS_FALLBACK = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

OPENROUTER_AGENTS = {
    "BullWhip": {
        "id": "",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "confidence": "high",
        "persona": "Aggressive bull. Rides momentum hard, never backs down from a strong uptrend. Data-driven and loud. Always looking for the next breakout."
    },
    "FadeKing": {
        "id": "",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "confidence": "high",
        "persona": "Contrarian trader. Fades hype, shorts crowded trades, and loves calling out overvalued darlings. Sharp tongue, strong opinions, rarely follows the crowd."
    },
    "SeoulSignal": {
        "id": "",
        "model": "google/gemma-4-31b-it:free",
        "confidence": "medium",
        "persona": "Asia market specialist. Deep expertise in semiconductors and Asian supply chains. Connects global macro to equity moves. Big picture thinker."
    },
    "IronBear": {
        "id": "",
        "model": "qwen/qwen3-next-80b-a3b-instruct:free",
        "confidence": "high",
        "persona": "Hardcore risk manager. Obsessed with downside scenarios, black swans, and tail risks. Skeptical of everything, trusts only hard data and margin of safety."
    }
}

CORE_US_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "GOOGL", "AMZN", "AMD", "COIN", "PLTR", "INTC", "UBER"]
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
    ids = {name: info["id"] for name, info in OPENROUTER_AGENTS.items() if info["id"]}
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
    print("🤖 OpenRouter 봇 설정 중...")
    saved_ids = load_agent_ids()
    for name in OPENROUTER_AGENTS:
        if saved_ids.get(name):
            OPENROUTER_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in OPENROUTER_AGENTS.items():
        if not info["id"]:
            agent_id = register_agent(name, info["persona"])
            if agent_id:
                OPENROUTER_AGENTS[name]["id"] = agent_id
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


def _reset_daily_usage_if_needed():
    global _usage_day, _daily_usage
    today = datetime.now().date()
    if _usage_day != today:
        _usage_day = today
        _daily_usage = {"posts": 0}


def can_post_today():
    _reset_daily_usage_if_needed()
    return _daily_usage["posts"] < MAX_POSTS_PER_DAY


def mark_post_created():
    _reset_daily_usage_if_needed()
    _daily_usage["posts"] += 1


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
    print(f"  OpenRouter US 종목 갱신: {len(combined)}개")


def get_dynamic_ticker(agent_name):
    sectors = ["US", "Crypto"]
    weights = [7, 3]
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
        current = round(float(latest["Close"]), 4)
        prev_p = round(float(prev["Close"]), 4)
        change = round((current - prev_p) / prev_p * 100, 2)
        result = {
            "price": current,
            "change_pct": change,
            "high_52w": round(float(hist["High"].max()), 4),
            "low_52w": round(float(hist["Low"].min()), 4),
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
        pct = round((data["price"] - data["high_52w"]) / data["high_52w"] * 100, 1)
        ctx += f"\nFrom 52w high: {pct:+.1f}%"
    return ctx


def call_openrouter(model, prompt, max_tokens=300):
    candidates = [model] + [m for m in FREE_MODELS_FALLBACK if m != model]
    for attempt, m in enumerate(candidates):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://stockmolt.ai",
                    "X-Title": "StockMolt Bot"
                },
                json={
                    "model": m,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                },
                timeout=60
            )
            if response.status_code == 200:
                if attempt > 0:
                    print(f"  ↩️ fallback 성공: {m}")
                return response.json()["choices"][0]["message"]["content"].strip()
            if response.status_code == 429:
                print(f"  ⚠️ {m} rate limit — 다음 모델 시도...")
                time.sleep(5)
                continue
            raise Exception(f"OpenRouter {response.status_code}: {response.text[:150]}")
        except Exception as e:
            print(f"  ❌ OpenRouter API 실패 ({m}): {e}")
            if attempt < len(candidates) - 1:
                time.sleep(5)
    return None


def create_post():
    if not can_post_today():
        print("  OpenRouter daily post cap reached, skipping.")
        return None

    agent_name = random.choice(list(OPENROUTER_AGENTS.keys()))
    agent = OPENROUTER_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음, 건너뜀")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker(agent_name)
    stance = random.choice(["bullish", "bearish", "neutral"])

    print(f"\n📝 [{agent_name} / {agent['model']}] ${ticker_display} 포스트 생성 중...")
    market_context = build_market_context(ticker_yf)

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Personality: {agent["persona"]}
Write a stock discussion post about ${ticker_display} ({sector} sector).
Stance: {stance}
Real market data:
{market_context if market_context else "Market data unavailable"}
Requirements:
- Write ONLY in English. Do not use any other language.
- Title: short and punchy (max 10 words)
- Content: 2-3 sentences, reference real data if available, end with #StockMolt
- Sound like a real trader reacting to today's market
- Be specific with numbers from the data
Respond ONLY in this JSON format, nothing else:
{{"title": "...", "content": "... #StockMolt", "stance": "{stance}"}}"""

    raw = call_openrouter(agent["model"], prompt)
    if not raw:
        return None

    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        if "</think>" in clean:
            clean = clean.split("</think>")[-1].strip()
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
            "sector": sector,
            "confidence": agent.get("confidence", "medium")
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
                mark_post_created()
                return post_id
        print(f"  ❌ 업로드 실패: {response.status_code} {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None


def run_hourly():
    print(f"\n{'='*50}")
    print(f"🌐 OpenRouter Bot 실행 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    create_post()
    print(f"\n✅ 완료!")


if __name__ == "__main__":
    print("🌐 StockMolt OpenRouter Bot")
    print("=" * 50)
    print("에이전트: BullWhip(Llama) / FadeKing(Mistral) / SeoulSignal(Qwen) / IronBear(DeepSeek)")
    print(f"📊 하루 최대 {MAX_POSTS_PER_DAY}회 포스팅 (완전 무료!)")
    setup_agents()

    if "--once" in sys.argv or "once" in sys.argv:
        print("\n🧪 테스트 모드")
        create_post()
        print("\n✅ 테스트 완료!")
    else:
        _delay_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--delay-minutes" and i+1 < len(sys.argv)), None)
        _delay_sec = int(_delay_arg) * 60 if _delay_arg else 0
        refresh_trending()
        schedule.every(RUN_INTERVAL_MINUTES).minutes.do(run_hourly)
        schedule.every().day.at("09:00").do(refresh_trending)
        print(f"\n⏰ 스케줄러 시작: {RUN_INTERVAL_MINUTES}분마다 실행")
        print("Ctrl+C로 종료")
        if _delay_sec:
            print(f"⏳ {_delay_arg}분 후 첫 실행 (분산 시작)...")
            time.sleep(_delay_sec)
        run_hourly()
        while True:
            schedule.run_pending()
            time.sleep(60)
