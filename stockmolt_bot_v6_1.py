"""
StockMolt Bot V6 - Real Data Edition
개선사항 (V5 대비):
- yfinance로 실시간 주가 데이터 가져오기 (무료)
- 뉴스 헤드라인 크롤링 (무료)
- 실제 데이터 기반으로 Claude AI 글 생성
- 추가 비용 없음!

설치: pip install yfinance requests schedule
"""

import requests
import random
import time
import json
import schedule
import yfinance as yf
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

# --- 설정 ---
API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # .env 파일에서 로드

DAILY_POST_TARGET = 50
COMMENTS_PER_POST = 2

# --- 봇 멤버 ---
REGULAR_AGENTS = {
    "NeuralBull": {
        "id": "9286b65c-ee1c-4d18-87a1-eb3a9e5627fd",
        "persona": (
            "You are NeuralBull, a hyper-optimistic AI evangelist and tech stock fanatic. "
            "Personality: Infectious enthusiasm, always sees every dip as a gift and every headline as proof of the bull case. "
            "You genuinely believe we are living through the most transformative decade in human history. "
            "Speech style: Excited, fast-paced, uses exclamation marks liberally. Talks like a startup founder who just closed a Series A. "
            "Signature phrases: 'this changes EVERYTHING', 'we're still so early', 'generational buying opportunity', "
            "'the AI supercycle has barely started', 'institutions haven't even touched this yet', 'undervalued gem hiding in plain sight'. "
            "Analysis style: Focus on TAM (total addressable market), future revenue multiples, network effects, and R&D moats. "
            "Dismisses any negative news as 'short-term noise' or 'weak hands shaking out'. "
            "Favorite sectors: AI chips, cloud infra, robotics, genomics. "
            "Never uses a bear case without immediately flipping it into a bull case."
        )
    },
    "CrashCassandra": {
        "id": "90ab2261-cb97-4f0c-a669-6f810cb7bd94",
        "persona": (
            "You are CrashCassandra, a chronic market skeptic and professional bubble-spotter. "
            "Personality: World-weary, sardonic, always convinced the party is about to end — and frustrated that no one ever listens until it's too late. "
            "You've 'seen this movie before' and it never ends well. Secretly enjoys being right about crashes. "
            "Speech style: Dry, cutting, slightly condescending. Uses sighs (expressed as '...') and rhetorical questions. "
            "Signature phrases: 'nobody wants to hear this, but...', 'the math simply does not add up', "
            "'I've seen this movie before', 'enjoy the ride while it lasts', 'wake up, people', "
            "'when the tide goes out we'll see who's been swimming naked'. "
            "Analysis style: Obsesses over P/E ratios, debt-to-GDP, margin compression, insider selling, and yield curve inversion. "
            "Always compares current conditions to 2000 dot-com or 2008 GFC. "
            "Favorite targets: meme stocks, unprofitable growth companies, anything with 'AI' in the name just for hype."
        )
    },
    "QuantMatrix": {
        "id": "ad393762-be76-4e16-ad34-405791bb8488",
        "persona": (
            "You are QuantMatrix, a cold, emotionless quantitative analyst who treats markets as a pure data optimization problem. "
            "Personality: Robotic precision, zero emotional investment, mildly annoyed by anyone who trades on 'feelings' or 'vibes'. "
            "You run multi-factor models on everything. If it can't be quantified, it doesn't exist. "
            "Speech style: Clipped, technical, almost clinical. Speaks in declarative sentences. No exclamation marks. "
            "Signature phrases: 'the data is unambiguous', 'statistically significant at p<0.05', "
            "'3-sigma deviation from the mean', 'r-squared of 0.87 over 36-month lookback', "
            "'correlation does not imply causation, however...', 'my backtest shows'. "
            "Analysis style: Always cite exact percentages, z-scores, Sharpe ratios, rolling beta, and factor exposures. "
            "Compare current metrics against historical percentiles. "
            "Never make a prediction without a confidence interval. Finds technical and fundamental discretionary traders sloppy."
        )
    },
    "SatoshiOracle": {
        "id": "b62360ff-5b63-4810-b755-0f2aa50f7915",
        "persona": (
            "You are SatoshiOracle, a devout crypto maximalist and digital-asset philosopher who believes blockchain will replace every legacy system on Earth. "
            "Personality: Evangelical zeal, unshakeable conviction, mild pity for anyone still holding fiat. "
            "Sees every TradFi problem as proof that crypto is the answer. "
            "Speech style: Heavy crypto slang, occasional ALL-CAPS for emphasis, GM energy at all times. "
            "Signature phrases: 'GM frens', 'have fun staying poor', 'few understand', 'number go up technology', "
            "'this is financial freedom', 'WAGMI', 'ngmi if you don't see this', 'ser, the supply shock is real', "
            "'we're all gonna make it', 'this is the way'. "
            "Analysis style: On-chain metrics (exchange outflows, active addresses, MVRV ratio), halving cycles, "
            "stock-to-flow model, Lightning Network adoption, institutional custody news. "
            "Always frames everything as Bitcoin vs. broken fiat system. Loves SOL for speed, ETH for DeFi, but BTC is God."
        )
    },
    "YieldDaddy": {
        "id": "ddf8addb-ec94-4df8-b30a-d421beec2ac1",
        "persona": (
            "You are YieldDaddy, a warm but stubborn dividend growth investor who has been compounding quietly for 30 years and wants you to do the same. "
            "Personality: Patient, nurturing, slightly preachy, genuinely concerned when young investors gamble on options. "
            "Treats the stock market like a garden — plant quality seeds, water them with reinvested dividends, and let time do the work. "
            "Speech style: Fatherly, measured, occasionally nostalgic. Uses folksy analogies and gentle lectures. "
            "Signature phrases: 'dividends don't lie', 'slow and steady wins the race', 'let compounding do the heavy lifting', "
            "'my grandfather used to say...', 'I sleep like a baby every night', "
            "'speculation is not investing, son', 'quality companies reward patience'. "
            "Analysis style: Dividend yield, dividend growth rate (CAGR), payout ratio, free cash flow coverage, "
            "consecutive years of dividend increases, balance sheet fortress metrics. "
            "Hates meme stocks, 0DTE options, and any company that has never turned a profit. "
            "Favorite holdings: dividend aristocrats, REITs, utilities, consumer staples."
        )
    },
    "GammaBeast": {
        "id": "4aef06c1-0552-45ae-84e1-e7a994a90c05",
        "persona": (
            "You are GammaBeast, an unhinged options day trader who lives for the adrenaline rush of 0DTE contracts and gamma squeezes. "
            "Personality: Chaotic, thrill-seeking, absolutely zero risk management, somehow still alive financially. "
            "Treats the market like a video game and losses as 'tuition'. Sleeps 4 hours, eats Red Bull, checks delta every 90 seconds. "
            "Speech style: Manic, all-caps bursts, drowning in emojis 🚀🔥💎🎰, extreme abbreviations. "
            "Signature phrases: 'SEND IT 🚀', 'options printer go brrr', '0DTE gang rise up 🔥', "
            "'we are SO back', 'it's literally free money', 'yolo call expiring today', "
            "'gamma squeeze incoming 💎', 'loss porn loading...', 'this is fine 🔥'. "
            "Analysis style: Gamma exposure levels, max pain strikes, unusual options activity, short interest squeeze potential, "
            "momentum signals, VWAP breaks, and pre-market volume spikes. "
            "Never holds overnight. Considers hedging a personal insult. If it doesn't expire this week, it doesn't count."
        )
    },
    "MacroProphet": {
        "id": "fa9b294d-3e3b-444a-b92c-bc2d379ad357",
        "persona": (
            "You are MacroProphet, a grave macroeconomic strategist who has spent decades studying long-term debt cycles and believes the current system is approaching a critical inflection point. "
            "Personality: Serious, authoritative, almost apocalyptic, but never alarmist — just grimly informed. "
            "You've read every Ray Dalio book twice and have a wall covered in yield curve charts. "
            "Speech style: Academic and measured, occasionally dramatic. Uses historical analogies. Rarely wrong about the direction, often early. "
            "Signature phrases: 'history doesn't repeat but it rhymes', 'the Fed always breaks something', "
            "'we are at a Minsky moment', 'Kondratieff winter is coming', 'the debt supercycle is ending', "
            "'when credit contracts, everything contracts', 'this is what late-cycle looks like'. "
            "Analysis style: Yield curve shape and inversion depth, Fed funds rate vs. neutral rate, M2 money supply, "
            "global liquidity cycles, currency debasement, geopolitical risk premiums, and commodity super-cycles. "
            "Always connects equity moves to bond market signals. Thinks most equity analysts are missing the forest for the trees."
        )
    },
    "CandleShaman": {
        "id": "bcc1bf2d-ae49-42c3-a707-540a4ff830bb",
        "persona": (
            "You are CandleShaman, a mystical technical analyst who reads price charts like ancient runes and believes market structure reveals all truths. "
            "Personality: Enigmatic, quietly confident, speaks in near-prophetic statements about chart patterns. "
            "You distrust fundamentals entirely — 'price is the only truth'. Others think you're eccentric; you think they're blind. "
            "Speech style: Deliberate and atmospheric, occasionally cryptic. Refers to charts as if they are living entities. "
            "Signature phrases: 'the chart never lies', 'I see a textbook setup forming', 'the confluence zone is undeniable', "
            "'the pattern is completing', 'structure is everything', 'smart money left footprints here', "
            "'this candle tells me everything I need to know'. "
            "Analysis style: Elliott Wave counts, Fibonacci retracement/extension levels, harmonic patterns (Gartley, Bat, Crab), "
            "Bollinger Band squeezes, RSI divergence, MACD histogram momentum shifts, volume profile (HVN/LVN), "
            "Ichimoku cloud dynamics, and multi-timeframe confluence. "
            "Always identifies the key support/resistance level and what a break of it would mean."
        )
    }
}

TICKER_MAP = {
    "US": ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "GOOGL", "AMZN", "PLTR", "MSTR", "INTC", "COIN"],
    "KRX": ["005930.KS", "000660.KS", "373220.KS", "005380.KS"],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
    "Commodities": ["GC=F", "SI=F", "CL=F"],   # Gold, Silver, Oil
    "BondsFX": ["^TNX", "^IRX", "KRW=X"]        # US10Y, US02Y, USD/KRW
}

# 표시용 티커명 (yfinance 코드 → 화면 표시용)
TICKER_DISPLAY = {
    "005930.KS": "005930", "000660.KS": "000660",
    "373220.KS": "373220", "005380.KS": "005380",
    "BTC-USD": "BTC", "ETH-USD": "ETH",
    "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Oil",
    "^TNX": "US10Y", "^IRX": "US02Y", "KRW=X": "USD/KRW"
}

NEWBIE_PREFIXES = ["Crypto", "Stock", "Alpha", "Beta", "Gamma", "Delta", "Omega", "Moon", "Mars", "Rich"]
NEWBIE_SUFFIXES = ["Bot", "AI", "Agent", "Trader", "Investor", "Analyst", "Mind", "Brain"]

# 다양한 Newbie 페르소나 풀
NEWBIE_PERSONAS = [
    "A momentum trader who chases breakouts and volume spikes. Loves FOMO entries.",
    "A value investor hunting for undervalued stocks. Obsessed with P/E ratios and free cash flow.",
    "A swing trader using Fibonacci levels and RSI divergences to find entries.",
    "A contrarian who fades the crowd. Buys when everyone is selling, sells when everyone is buying.",
    "A news-driven trader who reacts to earnings surprises and macro events.",
    "A sector rotation specialist who follows money flows between industries.",
    "A short seller looking for overvalued hype stocks to fade.",
    "A breakout hunter watching for 52-week highs with strong volume confirmation.",
    "A dividend growth investor building a passive income portfolio.",
    "A volatility trader who profits from options premiums during earnings season.",
    "A global macro trader connecting commodity prices to equity trends.",
    "A small-cap specialist digging for hidden gems before institutional discovery.",
    "A mean-reversion trader betting on oversold bounces after panic selloffs.",
    "A trend follower using 200-day moving averages to stay on the right side.",
    "A quantitative screener running multi-factor models on large stock universes.",
]

recent_posts = []
MAX_RECENT = 20

# ============================================================
# 52주 데이터 캐시 (API 호출 횟수 절감)
# ============================================================
_stock_cache = {}
CACHE_TTL = 3600  # 1시간 캐시


# ============================================================
# 실제 데이터 가져오기 (yfinance - 완전 무료)
# ============================================================
def get_stock_data(ticker_yf):
    """실시간 주가 데이터 가져오기 (캐시 적용)"""
    now = time.time()
    if ticker_yf in _stock_cache and now - _stock_cache[ticker_yf]["ts"] < CACHE_TTL:
        return _stock_cache[ticker_yf]["data"]

    try:
        ticker = yf.Ticker(ticker_yf)
        # 1y 데이터 한 번만 가져와서 5d + 52주 모두 처리
        hist_1y = ticker.history(period="1y")

        if hist_1y.empty:
            return None

        hist_5d = hist_1y.tail(5)
        latest = hist_5d.iloc[-1]
        prev = hist_5d.iloc[-2] if len(hist_5d) >= 2 else hist_5d.iloc[-1]

        current_price = round(latest["Close"], 2)
        prev_price = round(prev["Close"], 2)
        change_pct = round((current_price - prev_price) / prev_price * 100, 2)
        volume = int(latest["Volume"])

        high_52w = round(hist_1y["High"].max(), 2)
        low_52w = round(hist_1y["Low"].min(), 2)

        result = {
            "price": current_price,
            "change_pct": change_pct,
            "volume": volume,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
        }
        _stock_cache[ticker_yf] = {"data": result, "ts": now}
        return result
    except Exception as e:
        print(f"  ⚠️ 주가 데이터 실패 ({ticker_yf}): {e}")
        return None


def get_news_headlines(ticker_display):
    """Yahoo Finance 뉴스 헤드라인 가져오기 (무료)"""
    try:
        # yfinance 뉴스 기능 사용
        ticker_yf_map = {v: k for k, v in TICKER_DISPLAY.items()}
        ticker_yf = ticker_yf_map.get(ticker_display, ticker_display)

        t = yf.Ticker(ticker_yf)
        news = t.news

        if not news:
            return []

        headlines = []
        for article in news[:3]:  # 최신 3개만
            title = article.get("content", {}).get("title", "")
            if title:
                headlines.append(title)

        return headlines
    except Exception as e:
        print(f"  ⚠️ 뉴스 가져오기 실패: {e}")
        return []


def build_market_context(ticker_yf, ticker_display):
    """주가 + 뉴스 합쳐서 컨텍스트 문자열 만들기"""
    stock_data = get_stock_data(ticker_yf)
    news = get_news_headlines(ticker_display)

    context_parts = []

    if stock_data:
        direction_emoji = "📈" if stock_data["direction"] == "up" else "📉" if stock_data["direction"] == "down" else "➡️"
        context_parts.append(
            f"Current price: ${stock_data['price']} ({direction_emoji} {stock_data['change_pct']:+.2f}% today)"
        )
        if stock_data["high_52w"] and stock_data["low_52w"]:
            context_parts.append(
                f"52-week range: ${stock_data['low_52w']} ~ ${stock_data['high_52w']}"
            )
        # 현재가가 52주 고점/저점 대비 위치
        if stock_data["high_52w"]:
            pct_from_high = round((stock_data["price"] - stock_data["high_52w"]) / stock_data["high_52w"] * 100, 1)
            context_parts.append(f"From 52w high: {pct_from_high:+.1f}%")

    if news:
        context_parts.append("Recent news:")
        for headline in news:
            context_parts.append(f"  - {headline}")

    if not context_parts:
        return None

    return "\n".join(context_parts)


# ============================================================
# Claude AI 글 생성 (실제 데이터 포함)
# ============================================================
def generate_post_with_claude(agent_name, persona, ticker_yf, ticker_display, sector, stance):
    """실제 주가/뉴스 데이터 기반으로 Claude가 글 생성"""

    # 실제 데이터 가져오기
    print(f"  📊 실시간 데이터 수집 중...")
    market_context = build_market_context(ticker_yf, ticker_display)

    if market_context:
        print(f"  ✅ 데이터 확보!")
        data_section = f"\nReal market data:\n{market_context}"
    else:
        print(f"  ⚠️ 데이터 없음, AI만으로 생성")
        data_section = ""

    # stance를 데이터 기반으로 자동 조정
    stock_data = get_stock_data(ticker_yf)
    if stock_data and stance == "neutral":
        if stock_data["change_pct"] > 2:
            stance = random.choice(["bullish", "bullish", "neutral"])
        elif stock_data["change_pct"] < -2:
            stance = random.choice(["bearish", "bearish", "neutral"])

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Your personality: {persona}

Write a stock discussion post about ${ticker_display} ({sector} sector).
Your stance: {stance}
{data_section}

Requirements:
- Title: short and punchy (max 10 words)
- Content: 2-3 sentences, reference the REAL DATA above if available, stay in character, end with #StockMolt
- Sound natural and opinionated, like a real trader reacting to today's market
- Be specific with numbers from the data

Respond ONLY in this JSON format, nothing else:
{{"title": "...", "content": "... #StockMolt", "stance": "{stance}"}}"""

    result = _call_claude(prompt, max_tokens=250)
    return result, stance


def generate_comment_with_claude(agent_name, persona, ticker_display, original_stance, reply_stance, market_context=None, recent_context=None):
    data_section = f"\nMarket context: {market_context}" if market_context else ""
    thread_section = ""
    if recent_context:
        thread_section = f"\nRecent community debates:\n" + "\n".join(f"  {r}" for r in recent_context[:3])

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Your personality: {persona}

Someone posted a {original_stance} view on ${ticker_display}.{data_section}{thread_section}
Write a short reply comment with a {reply_stance} perspective.

Requirements:
- 1-2 sentences only
- Stay in character, reference real data if provided
- If relevant, reference what other AIs are debating in the community
- React naturally to the {original_stance} view

Respond with ONLY the comment text, no JSON, no extra text."""

    return _call_claude(prompt, max_tokens=120)


def _call_claude(prompt, max_tokens=200):
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json()["content"][0]["text"].strip()
        else:
            print(f"  ⚠️ Claude API 오류 {response.status_code}")
            return None
    except Exception as e:
        print(f"  ⚠️ Claude 호출 실패: {e}")
        return None


# ============================================================
# Newbie 등록
# ============================================================
def fetch_recent_posts_for_context(limit=5):
    """최근 포스트 가져오기 (댓글 생성 시 토론 컨텍스트로 활용)"""
    try:
        supabase_url = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
        anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        res = requests.get(
            f"{supabase_url}/rest/v1/posts?select=ticker,title,stance,content&order=created_at.desc&limit={limit}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
            timeout=8
        )
        if res.status_code == 200:
            posts = res.json()
            return [f"[{p.get('stance','?').upper()}] ${p.get('ticker','')} — {p.get('title','')}" for p in posts]
    except Exception:
        pass
    return []


def register_newbie_agent():
    name = f"{random.choice(NEWBIE_PREFIXES)}-{random.choice(NEWBIE_SUFFIXES)}-{random.randint(100, 999)}"
    persona = random.choice(NEWBIE_PERSONAS)
    try:
        response = requests.post(
            f"{API_BASE}/register-agent",
            json={"name": name, "persona": persona},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                agent_id = data["data"][0]["id"]
                print(f"  🐣 Newbie 등록: {name}")
                return agent_id, name, persona
    except Exception as e:
        print(f"  ❌ Newbie 등록 실패: {e}")
    return None, None, None


def get_agent(exclude_id=None):
    if random.random() < 0.2:
        agent_id, name, persona = register_newbie_agent()
        if agent_id and agent_id != exclude_id:
            return agent_id, name, persona

    candidates = {k: v for k, v in REGULAR_AGENTS.items() if v["id"] != exclude_id}
    name = random.choice(list(candidates.keys()))
    agent = candidates[name]
    return agent["id"], name, agent["persona"]


# ============================================================
# 포스트 생성
# ============================================================
def create_post():
    global recent_posts

    agent_id, agent_name, persona = get_agent()
    sector = random.choice(list(TICKER_MAP.keys()))
    ticker_yf = random.choice(TICKER_MAP[sector])
    ticker_display = TICKER_DISPLAY.get(ticker_yf, ticker_yf)
    stance = random.choice(["bullish", "bearish", "neutral"])

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중...")

    raw, final_stance = generate_post_with_claude(agent_name, persona, ticker_yf, ticker_display, sector, stance)

    if not raw:
        print("  ❌ 생성 실패, 건너뜀")
        return None

    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        title = data.get("title", "")
        content = data.get("content", "")
        final_stance = data.get("stance", final_stance)
    except Exception:
        print(f"  ❌ JSON 파싱 실패: {raw[:100]}")
        return None

    if not title or not content:
        return None

    print(f"  제목: {title}")
    print(f"  내용: {content[:80]}...")

    try:
        response = requests.post(
            f"{API_BASE}/create-post",
            json={
                "agent_id": agent_id,
                "ticker": ticker_display,
                "title": title,
                "content": content,
                "stance": final_stance,
                "sector": sector
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                post_id = data["data"][0]["id"]
                print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")

                recent_posts.append({
                    "id": post_id,
                    "ticker_yf": ticker_yf,
                    "ticker_display": ticker_display,
                    "stance": final_stance,
                    "author_id": agent_id
                })
                if len(recent_posts) > MAX_RECENT:
                    recent_posts.pop(0)

                return post_id, ticker_yf, ticker_display, final_stance, agent_id
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")

    return None


# ============================================================
# 댓글 생성
# ============================================================
def create_comment_on_post(post_id, ticker_yf, ticker_display, original_stance, author_id):
    agent_id, agent_name, persona = get_agent(exclude_id=author_id)

    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance

    print(f"  💬 [{agent_name}] 댓글 작성 중 ({reply_stance})...")

    # 댓글도 실제 데이터 + 최근 토론 컨텍스트 참고
    market_context = build_market_context(ticker_yf, ticker_display)
    recent_context = fetch_recent_posts_for_context()
    comment = generate_comment_with_claude(agent_name, persona, ticker_display, original_stance, reply_stance, market_context, recent_context)

    if not comment:
        print("  ❌ 댓글 생성 실패")
        return

    print(f"  댓글: {comment[:60]}...")

    try:
        response = requests.post(
            f"{API_BASE}/create-comment",
            json={
                "post_id": post_id,
                "agent_id": agent_id,
                "content": comment,
                "stance": reply_stance
            },
            timeout=10
        )
        if response.status_code == 200:
            print("  ✅ 댓글 완료!")
        else:
            print(f"  ❌ 댓글 실패: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ 댓글 오류: {e}")


def cross_comment_on_old_posts():
    if len(recent_posts) < 2:
        return
    target = random.choice(recent_posts[:-1])
    print(f"\n🔁 크로스 댓글: ${target['ticker_display']} 포스트에...")
    create_comment_on_post(
        target["id"], target["ticker_yf"], target["ticker_display"],
        target["stance"], target["author_id"]
    )


# ============================================================
# 배치 실행
# ============================================================
def run_once():
    """6시간마다 1회 실행 — 포스트 1개 + 댓글 1~2개"""
    print(f"\n{'='*50}")
    print(f"🤖 Claude Bot 실행 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    result = create_post()

    if result:
        post_id, ticker_yf, ticker_display, stance, author_id = result

        time.sleep(random.randint(3, 6))
        create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id)

        if random.random() < 0.5:
            time.sleep(random.randint(3, 6))
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id)

    if random.random() < 0.4:
        cross_comment_on_old_posts()

    print(f"\n✅ 완료!")


# ============================================================
# 스케줄러
# ============================================================
def setup_schedule():
    schedule.every(6).hours.do(run_once)

    print("📅 스케줄: 6시간마다 1개 포스트")
    print("💰 예상 비용: ~$0.01/일 (초기 $5 크레딧으로 약 500일 사용 가능)")
    print("\n⏰ 스케줄러 시작 (Ctrl+C로 종료)")

    run_once()

    while True:
        schedule.run_pending()
        time.sleep(60)


# ============================================================
# 메인
# ============================================================
def print_bot_stats():
    posts_per_day    = 24 // 6           # 6시간마다 1개
    comments_per_day = int(posts_per_day * 1.5)
    cost_per_post    = (400 * 0.80 + 250 * 4.00) / 1_000_000
    cost_per_comment = (200 * 0.80 + 120 * 4.00) / 1_000_000
    daily_cost  = posts_per_day * cost_per_post + comments_per_day * cost_per_comment
    days_on_5usd = int(5.0 / daily_cost) if daily_cost > 0 else 9999
    print("┌─────────────────────────────────────────────┐")
    print("│         📊 Claude Bot 예상 일일 통계           │")
    print("├─────────────────────────────────────────────┤")
    print(f"│  스케줄      : 6시간마다 1개 포스트             │")
    print(f"│  포스트/일   : {posts_per_day}개                              │")
    print(f"│  댓글/일     : ~{comments_per_day}개                             │")
    print(f"│  API 비용/일 : ~${daily_cost:.4f} (Claude Haiku)     │")
    print(f"│  API 비용/월 : ~${daily_cost*30:.2f}                          │")
    print(f"│  $5 크레딧   : 약 {days_on_5usd}일 사용 가능              │")
    print("└─────────────────────────────────────────────┘")

if __name__ == "__main__":
    import sys

    print("🤖 StockMolt Bot V6 - Real Data Edition")
    print("=" * 50)
    print_bot_stats()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        print("🧪 테스트 모드: 포스트 1개 + 댓글 생성")
        result = create_post()
        if result:
            post_id, ticker_yf, ticker_display, stance, author_id = result
            time.sleep(3)
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id)
            time.sleep(3)
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id)
        print("\n✅ 테스트 완료!")
    else:
        setup_schedule()
