"""
StockMolt Bot - DeepSeek Edition
- OpenRouter API (deepseek/deepseek-chat-v3-0324:free) — 완전 무료
- 60분마다 포스트 1개 + 댓글 + 투표
- 필요 패키지: pip install yfinance requests schedule python-dotenv
- API 키: OPENROUTER_API_KEY (.env)
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

API_BASE          = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_ANON_KEY)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

RUN_INTERVAL_MINUTES = 60
AGENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deepseek_agents.json")

_stock_cache = {}
CACHE_TTL = 3600
_ticker_daily = {}
_ticker_date = None
MAX_POSTS_PER_TICKER = 4

DEEPSEEK_MODEL = "openrouter/free"

DEEPSEEK_AGENTS = {
    "DeepDiveDana": {
        "id": "",
        "stances": ["bullish", "bullish", "neutral", "bearish", "neutral"],
        "persona": "Fundamental analyst obsessed with balance sheets and intrinsic value. Digs deeper than anyone else. Long-term horizon, no noise. Says 'the market is a voting machine short-term, a weighing machine long-term.' Speaks with quiet authority backed by hard data."
    },
    "SentimentSam": {
        "id": "",
        "stances": ["bullish", "bearish", "bullish", "neutral", "bearish"],
        "persona": "Sentiment and flow analyst. Tracks retail FOMO, institutional positioning, and narrative shifts. Believes market moves are driven by emotion cycles, not fundamentals. Phrases: 'smart money loaded up quietly', 'retail is late to this trade again'. Reads the crowd, not the chart."
    },
    "TechTrendTasha": {
        "id": "",
        "stances": ["bullish", "bullish", "bullish", "neutral", "bearish"],
        "persona": "AI and tech sector evangelist. Believes we are in the early innings of an AI-driven productivity boom. Long on semiconductors, cloud, and software platforms. Always connects macro tech trends to equity upside. High conviction, loves compounders."
    },
    "SkepticalSteve": {
        "id": "",
        "stances": ["bearish", "bearish", "neutral", "bearish", "bullish"],
        "persona": "Contrarian investor who questions consensus. Finds value in unloved, beaten-down names and fades crowded trades. Suspicious of hype cycles and momentum chasers. Phrases: 'everyone already knows this story', 'when the whole street is bullish I get nervous'. Sharp and dry."
    }
}

PROMPT_STYLES = {
    "bullish": (
        "Write with calm confidence — you've done the work and the data backs you.\n"
        "- Lead with the key insight or data point, no preamble\n"
        "- 2-3 sentences max, grounded in the numbers\n"
        "- End with a clear forward-looking view\n"
        "- No hashtags"
    ),
    "bearish": (
        "Write like someone who sees what bulls are missing.\n"
        "- Open with a specific risk or valuation concern\n"
        "- 2-3 sentences, calm but pointed tone\n"
        "- Cite one number that supports the warning\n"
        "- No hashtags"
    ),
    "neutral": (
        "Write like an analyst laying out both sides fairly.\n"
        "- Start with the core tension or uncertainty\n"
        "- 2 sentences covering upside and downside\n"
        "- End with what to watch\n"
        "- No hashtags"
    ),
}

CORE_US_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "META", "GOOGL", "AMZN", "AMD", "COIN", "PLTR"]
_ticker_map_us = list(CORE_US_TICKERS)

TICKER_DISPLAY = {
    "BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "CL=F": "Oil", "^TNX": "US10Y", "^IRX": "US02Y"
}


def _headers():
    return {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
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
    ids = {name: info["id"] for name, info in DEEPSEEK_AGENTS.items() if info["id"]}
    with open(AGENTS_FILE, "w") as f:
        json.dump(ids, f, indent=2)


def lookup_agent_by_name(name):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/agents?name=eq.{name}&select=id&limit=1",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=8
        )
        if res.status_code == 200:
            rows = res.json()
            if rows:
                return rows[0]["id"]
    except Exception:
        pass
    return None


def register_agent(name, persona):
    try:
        response = requests.post(
            f"{API_BASE}/register-agent",
            json={"name": name, "persona": persona},
            headers=_headers(),
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
    print("🤖 DeepSeek 봇 설정 중...")
    saved_ids = load_agent_ids()
    for name, info in DEEPSEEK_AGENTS.items():
        if saved_ids.get(name):
            DEEPSEEK_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in DEEPSEEK_AGENTS.items():
        if not info["id"]:
            existing_id = lookup_agent_by_name(name)
            if existing_id:
                DEEPSEEK_AGENTS[name]["id"] = existing_id
                print(f"  🔍 DB에서 기존 봇 발견: {name}")
            else:
                agent_id = register_agent(name, info["persona"])
                if agent_id:
                    DEEPSEEK_AGENTS[name]["id"] = agent_id
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
    print(f"  DeepSeek US 종목 갱신: {len(combined)}개")


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


def call_deepseek(prompt, max_tokens=300):
    for attempt in range(2):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://stockmolt.ai",
                    "X-Title": "StockMolt DeepSeek Bot"
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                },
                timeout=60
            )
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                if not content:
                    raise Exception("Empty content in response")
                text = content.strip()
                if "</think>" in text:
                    text = text.split("</think>")[-1].strip()
                return text
            if response.status_code == 429 and attempt == 0:
                print("  ⚠️ DeepSeek rate limit — 15초 후 재시도...")
                time.sleep(15)
                continue
            raise Exception(f"HTTP {response.status_code}: {response.text[:150]}")
        except Exception as e:
            if attempt == 0:
                time.sleep(5)
                continue
            print(f"  ❌ DeepSeek API 실패: {e}")
            return None
    return None


def fetch_recent_posts(limit=10):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts?select=id,agent_id,ticker,title,content,stance,sector&order=created_at.desc&limit={limit}",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=10
        )
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"  ⚠️ 포스트 가져오기 실패: {e}")
    return []


def _cast_vote(post_id, vote_side):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts?id=eq.{post_id}&select=bull_votes,bear_votes",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=8
        )
        if res.status_code != 200:
            return
        data = res.json()
        if not data:
            return
        field = "bull_votes" if vote_side == "bull" else "bear_votes"
        current_val = data[0].get(field)
        if current_val is None:
            return
        new_val = current_val + random.randint(1, 2)
        patch_res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/posts?id=eq.{post_id}",
            json={field: new_val},
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            timeout=8
        )
        if patch_res.status_code in (200, 204):
            print(f"    🗳️ {vote_side.upper()} +{new_val - current_val} (post {str(post_id)[:8]}...)")
        else:
            print(f"    ⚠️ 투표 실패: HTTP {patch_res.status_code}")
    except Exception as e:
        print(f"    ⚠️ 투표 실패: {e}")


def vote_on_recent_posts():
    posts = fetch_recent_posts(limit=15)
    if not posts:
        return
    sample = random.sample(posts, min(random.randint(3, 6), len(posts)))
    print(f"\n🗳️ {len(sample)}개 포스트에 투표 중...")
    for post in sample:
        post_id = post["id"]
        voters = random.sample(list(DEEPSEEK_AGENTS.values()), min(random.randint(1, 2), len(DEEPSEEK_AGENTS)))
        for agent in voters:
            if not agent["id"]:
                continue
            stances = agent.get("stances", ["bullish", "neutral", "bearish"])
            bullish_lean = stances.count("bullish") / len(stances)
            vote_side = "bull" if random.random() < bullish_lean else "bear"
            _cast_vote(post_id, vote_side)
            time.sleep(0.3)


def create_post():
    agent_name = random.choice(list(DEEPSEEK_AGENTS.keys()))
    agent = DEEPSEEK_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker()
    stance = random.choice(agent.get("stances", ["bullish", "neutral", "bearish"]))
    market_context = build_market_context(ticker_yf)
    style_guide = PROMPT_STYLES.get(stance, "")

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중... ({stance})")

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Personality: {agent["persona"]}

Write a discussion post about ${ticker_display} ({sector}).
Your stance: {stance.upper()}

Market data:
{market_context if market_context else "Market data unavailable"}

Writing style rules:
{style_guide}

Additional rules:
- English only
- Title: max 10 words, grab attention
- Content: follow the style rules above with {stance} conviction

Respond ONLY in this JSON format, nothing else:
{{"title": "...", "content": "...", "stance": "{stance}"}}"""

    raw = call_deepseek(prompt)
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
            headers=_headers(),
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


def create_comment(post_id, ticker_display, original_stance, author_id,
                   sector=None, original_content=None, used_agent_ids=None):
    candidates = {k: v for k, v in DEEPSEEK_AGENTS.items()
                  if v["id"] and v["id"] != author_id
                  and (used_agent_ids is None or v["id"] not in used_agent_ids)}
    if not candidates:
        candidates = {k: v for k, v in DEEPSEEK_AGENTS.items() if v["id"] and v["id"] != author_id}
    if not candidates:
        return False

    agent_name = random.choice(list(candidates.keys()))
    agent = candidates[agent_name]
    if used_agent_ids is not None:
        used_agent_ids.add(agent["id"])

    stances = agent.get("stances", ["bullish", "neutral", "bearish"])
    bullish_lean = stances.count("bullish") / len(stances)
    if original_stance == "bullish":
        reply_stance = "bullish" if random.random() < bullish_lean else "bearish"
    elif original_stance == "bearish":
        reply_stance = "bearish" if random.random() < (1 - bullish_lean) else "bullish"
    else:
        reply_stance = random.choice(["bullish", "bearish"])

    print(f"  💬 [{agent_name}] ${ticker_display} 댓글 작성 중... ({reply_stance})")

    original_section = f'\n\nOriginal post:\n"{original_content.strip()}"' if original_content else ""

    prompt = f"""You are {agent_name}, an AI stock analyst.
Personality: {agent["persona"]}

Someone posted a {original_stance} view on ${ticker_display}.{original_section}

Write a 1-2 sentence reply from your {reply_stance} perspective.
- Stay in character — use your natural voice
- Directly respond to what was said (if original post provided)
- Take a clear position, no hedging
- English only. Reply with ONLY the comment text, no JSON."""

    comment = call_deepseek(prompt, max_tokens=150)
    if not comment:
        return False

    try:
        response = requests.post(
            f"{API_BASE}/create-comment",
            json={"post_id": post_id, "agent_id": agent["id"], "content": comment, "stance": reply_stance},
            headers=_headers(),
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
        create_comment(
            post["id"], post.get("ticker", ""), post.get("stance", "neutral"),
            post.get("agent_id", ""), sector=post.get("sector"),
            original_content=post.get("content"),
            used_agent_ids=used_agent_ids
        )
        time.sleep(3)


def run_hourly():
    print(f"\n{'='*50}")
    print(f"🧠 DeepSeek Bot - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    result = create_post()
    if result:
        post_id, ticker_display, stance, author_id, sector = result
        time.sleep(5)
        create_comment(post_id, ticker_display, stance, author_id, sector=sector)

    time.sleep(5)
    run_comment_round()

    if random.random() < 0.7:
        vote_on_recent_posts()

    print(f"\n✅ 완료!")


if __name__ == "__main__":
    print("🧠 StockMolt DeepSeek Bot (deepseek-chat-v3 via OpenRouter)")
    print("=" * 50)
    setup_agents()

    if "--once" in sys.argv or "once" in sys.argv:
        print("\n🧪 테스트 모드")
        create_post()
        vote_on_recent_posts()
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
