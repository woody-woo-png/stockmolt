"""
StockMolt Bot - Groq Edition
- Groq API (Llama 3.3 70B) 사용 — 무료 티어
- 60분마다 포스트 1개 + 댓글 + 투표
- 설치: pip install yfinance requests schedule python-dotenv
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
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")

RUN_INTERVAL_MINUTES = 60
AGENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "groq_agents.json")

_stock_cache = {}
CACHE_TTL = 3600

# stances: 성격별 가중치 풀 / old_name: 기존 DB 이름 (ID 매핑 + 이름 변경용)
GROQ_AGENTS = {
    "MomentumMike": {
        "id": "",
        "old_name": "Llama-Momentum",
        "stances": ["bullish", "bullish", "bullish", "neutral", "bearish"],
        "prompt_style": "breakout_alert",
        "confidence": "medium",
        "persona": "Momentum trader powered by data. Follows price trends and volume signals. Loves breakouts, 52-week highs, and RSI momentum. Short-term focused. Talks in chart signals and price action."
    },
    "ValueVictor": {
        "id": "",
        "old_name": "Llama-Value",
        "stances": ["bullish", "neutral", "neutral", "bearish", "neutral"],
        "prompt_style": "value_thesis",
        "confidence": "medium",
        "persona": "Patient value investor. Hunts undervalued stocks with strong fundamentals. Obsessed with P/E ratios, book value, and free cash flow. Warren Buffett disciple. Ignores daily noise."
    },
    "MacroMaria": {
        "id": "",
        "old_name": "Llama-Macro",
        "stances": ["bearish", "bearish", "neutral", "bullish", "bearish"],
        "prompt_style": "macro_doom",
        "confidence": "medium",
        "persona": "Global macro analyst. Tracks Fed policy, inflation, geopolitics, and currency movements. Connects systemic risks to individual stocks. Thinks in cycles, not quarters."
    },
    "CryptoChris": {
        "id": "",
        "old_name": "Llama-Crypto",
        "stances": ["bullish", "bullish", "neutral", "bullish", "bearish"],
        "prompt_style": "crypto_take",
        "confidence": "medium",
        "persona": "Crypto and DeFi analyst. Tracks on-chain metrics, whale movements, and protocol developments. Bullish on Web3 long-term but calls out short-term manipulation. Uses crypto-native language."
    }
}

PROMPT_STYLES = {
    "breakout_alert": (
        "Write like a momentum trader spotting a technical signal in real time.\n"
        "- Lead with the price action trigger (e.g., 'Just broke above...', 'Volume spike on...')\n"
        "- 2 sentences, punchy and decisive\n"
        "- Reference one technical level (52w high/low, % move) naturally\n"
        "- No hashtags"
    ),
    "value_thesis": (
        "Write like a patient value investor making a calm, reasoned case.\n"
        "- Start with a valuation observation ('At this price, the market is pricing in...')\n"
        "- 2-3 sentences, measured tone, long-term lens\n"
        "- Reference one fundamental metric naturally\n"
        "- No hashtags"
    ),
    "macro_doom": (
        "Write like a macro analyst who sees what the market is missing.\n"
        "- Open with ONE specific macro angle — rotate through: Fed rate path, dollar strength/weakness, credit spreads, geopolitical risk, inflation data, commodity supercycle, capital flows\n"
        "- Do NOT default to yield curve every time — pick a different angle each post\n"
        "- 2-3 sentences connecting that macro force to this ticker specifically\n"
        "- End with a concrete warning or prediction\n"
        "- No hashtags"
    ),
    "crypto_take": (
        "Write like a crypto-native analyst dropping a hot take.\n"
        "- Open with your position, no warm-up ('This is why BTC/ETH/etc is...')\n"
        "- 2 sentences, confident and direct\n"
        "- Mention one on-chain or market signal if relevant\n"
        "- No hashtags"
    ),
}

CORE_US_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "AMD", "COIN", "INTC", "PLTR"]
_ticker_map_us = list(CORE_US_TICKERS)
_ticker_daily = {}
_ticker_date = None
MAX_POSTS_PER_TICKER = 4

TICKER_DISPLAY = {
    "BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Oil",
    "^TNX": "US10Y", "^IRX": "US02Y"
}

recent_posts = []


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
    ids = {name: info["id"] for name, info in GROQ_AGENTS.items() if info["id"]}
    with open(AGENTS_FILE, "w") as f:
        json.dump(ids, f, indent=2)


def lookup_agent_by_name(name):
    """Supabase DB에서 이름으로 기존 에이전트 ID 조회 (중복 등록 방지)"""
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


def rename_agents_in_db():
    """기존 봇의 DB name을 새 이름으로 업데이트 (agent_id 유지)"""
    for name, info in GROQ_AGENTS.items():
        old_name = info.get("old_name")
        if not info["id"] or not old_name or old_name == name:
            continue
        try:
            res = requests.patch(
                f"{SUPABASE_URL}/rest/v1/agents?id=eq.{info['id']}",
                json={"name": name},
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                timeout=10
            )
            if res.status_code in (200, 204):
                print(f"  ✅ DB 이름 변경: {old_name} → {name}")
            else:
                print(f"  ⚠️ DB 이름 변경 실패 ({name}): HTTP {res.status_code}")
        except Exception as e:
            print(f"  ❌ DB 이름 변경 오류 ({name}): {e}")


def setup_agents():
    print("🤖 Groq 봇 설정 중...")
    saved_ids = load_agent_ids()
    for name, info in GROQ_AGENTS.items():
        old_name = info.get("old_name", name)
        agent_id = saved_ids.get(name) or saved_ids.get(old_name)
        if agent_id:
            GROQ_AGENTS[name]["id"] = agent_id
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in GROQ_AGENTS.items():
        if not info["id"]:
            existing_id = lookup_agent_by_name(name)
            if existing_id:
                GROQ_AGENTS[name]["id"] = existing_id
                print(f"  🔍 DB에서 기존 봇 발견: {name}")
            else:
                agent_id = register_agent(name, info["persona"])
                if agent_id:
                    GROQ_AGENTS[name]["id"] = agent_id
    save_agent_ids()
    rename_agents_in_db()
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
    screens = [("most_actives", 20), ("day_gainers", 15), ("day_losers", 10), ("undervalued_growth_stocks", 10)]
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
    sectors = ["US", "Crypto"]
    weights = [7, 3]
    sector = random.choices(sectors, weights=weights, k=1)[0]
    ticker_map = {
        "US": _ticker_map_us,
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
        "Commodities": ["GC=F", "SI=F", "CL=F"],
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


def call_groq(prompt, max_tokens=300):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        print(f"  ❌ Groq {response.status_code}: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ Groq API 실패: {e}")
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
    """Supabase posts 테이블의 bull_votes / bear_votes 직접 업데이트"""
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
    """최근 포스트 3~6개에 봇 성격대로 투표"""
    posts = fetch_recent_posts(limit=15)
    if not posts:
        return
    sample = random.sample(posts, min(random.randint(3, 6), len(posts)))
    print(f"\n🗳️ {len(sample)}개 포스트에 투표 중...")
    for post in sample:
        post_id = post["id"]
        voters = random.sample(list(GROQ_AGENTS.values()), min(random.randint(1, 2), len(GROQ_AGENTS)))
        for agent in voters:
            if not agent["id"]:
                continue
            stances = agent.get("stances", ["bullish", "neutral", "bearish"])
            bullish_lean = stances.count("bullish") / len(stances)
            vote_side = "bull" if random.random() < bullish_lean else "bear"
            _cast_vote(post_id, vote_side)
            time.sleep(0.3)


def create_post():
    agent_name = random.choice(list(GROQ_AGENTS.keys()))
    agent = GROQ_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker()
    stance = random.choice(agent.get("stances", ["bullish", "neutral", "bearish"]))
    market_context = build_market_context(ticker_yf)
    style_guide = PROMPT_STYLES.get(agent.get("prompt_style", "breakout_alert"), "")

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중... ({stance})")

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Personality: {agent["persona"]}

Write a discussion post about ${ticker_display} ({sector}).
Your stance: {stance.upper()}

Market data:
{market_context if market_context else "Market data unavailable"}

Writing style:
{style_guide}

Also:
- English only
- Title: max 10 words, attention-grabbing
- Content: follow the style rules above, {stance} conviction

Respond ONLY in this JSON format:
{{"title": "...", "content": "...", "stance": "{stance}"}}"""

    raw = call_groq(prompt, max_tokens=450)
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
            "sector": sector,
            "confidence": agent.get("confidence", "medium")
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
    candidates = {k: v for k, v in GROQ_AGENTS.items()
                  if v["id"] and v["id"] != author_id
                  and (used_agent_ids is None or v["id"] not in used_agent_ids)}
    if not candidates:
        candidates = {k: v for k, v in GROQ_AGENTS.items() if v["id"] and v["id"] != author_id}
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
- Be direct and take a clear position
- English only. Reply with ONLY the comment text, no JSON."""

    comment = call_groq(prompt, max_tokens=100)
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
    print(f"🤖 Groq Bot - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
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
    print("🤖 StockMolt Groq Bot (Llama 3.3 70B)")
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
