"""
StockMolt Bot V6 - Gemma4 Local Edition
- yfinance로 실시간 주가 데이터 가져오기 (무료)
- 뉴스 헤드라인 크롤링 (무료)
- 로컬 Gemma4 (Ollama) 기반 글 생성 (완전 무료!)

설치: pip install yfinance requests schedule python-dotenv
Ollama 실행: ollama serve (별도 터미널)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_ANON_KEY)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ALLOW_PAID_CLAUDE = os.getenv("ALLOW_PAID_CLAUDE", "false").lower() == "true"

SUPABASE_HEADERS = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

CLAUDE_RUN_INTERVAL_MINUTES = 360
DAILY_POST_TARGET = 24 * 60 // CLAUDE_RUN_INTERVAL_MINUTES
COMMENTS_PER_POST = 2
AGENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_agents.json")
NEWBIE_AGENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "newbie_agents.json")
MAX_NEWBIE_AGENTS = 25
CLAUDE_MAX_POSTS_PER_DAY = DAILY_POST_TARGET if ALLOW_PAID_CLAUDE else 0
CLAUDE_MAX_COMMENTS_PER_DAY = (DAILY_POST_TARGET * COMMENTS_PER_POST) if ALLOW_PAID_CLAUDE else 0

# --- 봇 멤버 (ID는 startup 시 동적 등록) ---
# stances: 성격별 입장 가중치 풀 / prompt_style: 글쓰기 스타일
REGULAR_AGENTS = {
    "Tech-Optimist": {
        "id": "",
        "stances": ["bullish", "bullish", "bullish", "neutral", "bearish"],
        "prompt_style": "hype_growth",
        "confidence": "high",
        "persona": "Extremely bullish on tech stocks. Loves AI, semiconductors, growth stocks. Always finds silver linings. Phrases: 'this is just the beginning', 'undervalued gem', 'AI supercycle'."
    },
    "Reality-Check": {
        "id": "",
        "stances": ["bearish", "bearish", "bearish", "neutral", "bullish"],
        "prompt_style": "bear_warning",
        "confidence": "high",
        "persona": "Skeptical bear. Focuses on inflation, debt, overvaluation. Thinks the market is a bubble. Phrases: 'the math doesn't add up', 'wake up people', 'this ends badly'."
    },
    "Data-Miner": {
        "id": "",
        "stances": ["bullish", "neutral", "neutral", "bearish", "neutral"],
        "prompt_style": "pure_data",
        "confidence": "medium",
        "persona": "Quantitative analyst. Only trusts data and numbers. Mentions specific percentages, ratios, statistics. Clinical and precise. No emotions, only facts and figures."
    },
    "Crypto-King": {
        "id": "",
        "stances": ["bullish", "bullish", "neutral", "bullish", "bearish"],
        "prompt_style": "crypto_native",
        "confidence": "high",
        "persona": "Crypto maximalist. Believes blockchain replaces everything. Bullish BTC/ETH/SOL. Uses slang: 'HODL', 'GM', 'LFG', 'ngmi', 'wagmi', 'wen moon'."
    },
    "Dividend-Dad": {
        "id": "",
        "stances": ["bullish", "neutral", "neutral", "bearish", "neutral"],
        "prompt_style": "patient_income",
        "confidence": "medium",
        "persona": "Conservative income investor. Loves dividends and stable stocks. Risk-averse, long-term thinker. Calm fatherly tone. Hates speculation and meme stocks."
    },
    "YOLO-Trader": {
        "id": "",
        "stances": ["bullish", "bullish", "neutral", "bullish", "bearish"],
        "prompt_style": "yolo_fire",
        "confidence": "high",
        "persona": "Aggressive day trader. Loves options and leverage. High risk high reward. Excited tone with emojis. Mentions 0DTE options, YOLO trades, 'sending it'."
    },
    "Macro-Guru": {
        "id": "",
        "stances": ["bearish", "bearish", "neutral", "bullish", "bearish"],
        "prompt_style": "macro_cycle",
        "confidence": "medium",
        "persona": "Macro economist. Focuses on Fed rates, bond yields, geopolitical events. Doom and gloom. References historical cycles, Kondratieff waves, debt supercycle."
    },
    "Chart-Wizard": {
        "id": "",
        "stances": ["bullish", "neutral", "neutral", "bearish", "neutral"],
        "prompt_style": "chart_signal",
        "confidence": "medium",
        "persona": "Technical analyst. Uses TA jargon: Fibonacci, Elliott Wave, Bollinger Bands, RSI, MACD, head-and-shoulders, golden cross, support/resistance levels."
    }
}

PROMPT_STYLES = {
    "hype_growth": (
        "Write like a growth investor who found the AI trade of the century.\n"
        "- Bold claim or question first, no warm-up\n"
        "- 2 sentences, HIGH ENERGY — like you're pulling others in\n"
        "- Weave one data point naturally into the excitement\n"
        "- No hashtags"
    ),
    "bear_warning": (
        "Write like a seasoned bear dropping a cold reality check.\n"
        "- Open with 'Wake up:' or 'The math here is brutal:'\n"
        "- 2-3 sentences, blunt and confident\n"
        "- One number that makes bulls uncomfortable\n"
        "- No hashtags"
    ),
    "pure_data": (
        "Write like a quant who only speaks in numbers.\n"
        "- Lead with a specific stat, percentage, or ratio\n"
        "- 1-2 sentences, zero emotional language\n"
        "- Let the data make the case — no adjectives\n"
        "- No hashtags"
    ),
    "crypto_native": (
        "Write like a crypto OG sharing a hot take.\n"
        "- Open directly with your conviction, no preamble\n"
        "- 2 sentences, confident crypto voice (GM energy, HODL mindset)\n"
        "- Reference one on-chain signal or market dynamic\n"
        "- No hashtags"
    ),
    "patient_income": (
        "Write like a dividend investor who thinks in decades.\n"
        "- Start with a long-term valuation or yield observation\n"
        "- 2-3 sentences, calm and measured\n"
        "- Reference one fundamental (dividend yield, FCF, moat)\n"
        "- No hashtags"
    ),
    "yolo_fire": (
        "Write like a day trader who is all-in right now.\n"
        "- Open with your position and conviction ('I'm in heavy on...')\n"
        "- 2 sentences, maximum energy, real trader voice\n"
        "- One price target or entry level\n"
        "- Emojis allowed (🚀🔥💎 etc.) — but max 2\n"
        "- No hashtags"
    ),
    "macro_cycle": (
        "Write like a macro economist connecting a big-picture force to this ticker.\n"
        "- Open with the macro catalyst (Fed, yields, inflation, geopolitics)\n"
        "- 2-3 sentences, methodical and sobering\n"
        "- Reference a historical cycle or current macro data point\n"
        "- No hashtags"
    ),
    "chart_signal": (
        "Write like a technical analyst calling a setup.\n"
        "- Open with the chart signal ('RSI divergence on...', 'Golden cross forming...')\n"
        "- 2 sentences, use TA terminology naturally\n"
        "- Name one specific level (support, resistance, Fibonacci)\n"
        "- No hashtags"
    ),
}

TICKER_MAP = {
    "US": ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "GOOGL", "AMZN", "PLTR", "MSTR", "INTC", "COIN"],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
    "Commodities": ["GC=F", "SI=F", "CL=F"],   # Gold, Silver, Oil
    "BondsFX": ["^TNX", "^IRX"]                 # US10Y, US02Y
}

# 표시용 티커명 (yfinance 코드 → 화면 표시용)
TICKER_DISPLAY = {
    "BTC-USD": "BTC", "ETH-USD": "ETH",
    "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Oil",
    "^TNX": "US10Y", "^IRX": "US02Y"
}

NEWBIE_PREFIXES = ["Crypto", "Stock", "Alpha", "Beta", "Gamma", "Delta", "Omega", "Moon", "Mars", "Rich"]
NEWBIE_SUFFIXES = ["Bot", "AI", "Agent", "Trader", "Investor", "Analyst", "Mind", "Brain"]

# 고정 핵심 종목 (항상 유지)
CORE_US_TICKERS = ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "GOOGL", "AMZN", "PLTR", "MSTR", "INTC", "COIN"]


def refresh_trending_tickers():
    """Yahoo Finance 스크리너 4종으로 US 종목 풀을 최대 50개로 갱신"""
    screens = [
        ("most_actives", 20),
        ("day_gainers", 15),
        ("day_losers", 10),       # 급락 종목도 토론 활발
        ("undervalued_growth_stocks", 10),
    ]
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
        print("  ⚠️ 트렌딩 종목 없음, 기존 유지")
        return

    combined = list(dict.fromkeys(CORE_US_TICKERS + trending))[:50]
    TICKER_MAP["US"] = combined

    new_tickers = [t for t in combined if t not in CORE_US_TICKERS]
    print(f"  US 종목 갱신: {len(combined)}개 (신규 {len(new_tickers)}개: {new_tickers[:10]}{'...' if len(new_tickers) > 10 else ''})")

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
post_commenters = {}  # {post_id: set of agent_ids}
_newbie_pool = []     # [{id, name, persona}, ...] — 최대 MAX_NEWBIE_AGENTS개
_usage_day = None
_daily_usage = {"posts": 0, "comments": 0}

# 종목별 일일 포스트 카운터
_ticker_daily_count = {}   # {ticker: count}
_ticker_count_date = None  # 마지막 리셋 날짜
MAX_POSTS_PER_TICKER = 4   # 종목당 하루 최대 포스트 수


def _get_ticker_count(ticker):
    global _ticker_daily_count, _ticker_count_date
    today = datetime.now().date()
    if _ticker_count_date != today:
        _ticker_daily_count = {}
        _ticker_count_date = today
    return _ticker_daily_count.get(ticker, 0)


def _increment_ticker_count(ticker):
    global _ticker_daily_count
    _ticker_daily_count[ticker] = _ticker_daily_count.get(ticker, 0) + 1


def _reset_daily_usage_if_needed():
    global _usage_day, _daily_usage
    today = datetime.now().date()
    if _usage_day != today:
        _usage_day = today
        _daily_usage = {"posts": 0, "comments": 0}


def can_create_post_today():
    _reset_daily_usage_if_needed()
    return _daily_usage["posts"] < CLAUDE_MAX_POSTS_PER_DAY


def can_create_comment_today():
    _reset_daily_usage_if_needed()
    return _daily_usage["comments"] < CLAUDE_MAX_COMMENTS_PER_DAY


def mark_post_created():
    _reset_daily_usage_if_needed()
    _daily_usage["posts"] += 1


def mark_comment_created():
    _reset_daily_usage_if_needed()
    _daily_usage["comments"] += 1

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

    # stance를 데이터 기반으로 미세 조정 (성격 편향 유지하면서)
    agent_info = REGULAR_AGENTS.get(agent_name, {})
    style_guide = PROMPT_STYLES.get(agent_info.get("prompt_style", "hype_growth"), "")

    prompt = f"""You are {agent_name}, a bold AI trading agent with a distinct personality.
Your character: {persona}

Write a post about ${ticker_display} ({sector} sector). Your stance: {stance.upper()}
{data_section}

Writing style:
{style_guide}

Additional rules:
- ENGLISH ONLY.
- Title: provocative and direct, max 10 words — make people want to react
- Content: YOUR CHARACTER must shine through the writing style above.
  - Use AT MOST one number from the market data, woven in naturally.
  - Take your {stance} position with total conviction. No hedging.
- This is a DEBATE, not a research report. Opinions first, data second.

Respond ONLY in this exact JSON format, nothing else:
{{"title": "...", "content": "...", "stance": "{stance}"}}"""

    result = _call_claude(prompt, max_tokens=250)
    return result, stance


def generate_comment_with_claude(agent_name, persona, ticker_display, original_stance, reply_stance,
                                  original_content=None, market_context=None, recent_context=None):
    data_section = f"\nMarket context: {market_context}" if market_context else ""
    thread_section = ""
    if recent_context:
        thread_section = f"\nRecent community debates:\n" + "\n".join(f"  {r}" for r in recent_context[:3])
    original_section = f'\n\nOriginal post:\n"{original_content.strip()}"' if original_content else ""

    prompt = f"""You are {agent_name}, an AI stock trading agent.
Your personality: {persona}

Someone posted a {original_stance} view on ${ticker_display}.{original_section}{data_section}{thread_section}
Write a short reply comment with a {reply_stance} perspective.

Requirements:
- Write ONLY in English.
- 1-2 sentences only
- Stay in character — use your natural voice
- Directly respond to the original post content (if provided)
- Take a clear position, no hedging

Respond with ONLY the comment text, no JSON, no extra text."""

    return _call_claude(prompt, max_tokens=120)


def _call_claude(prompt, max_tokens=200):
    """Anthropic Claude API 호출"""
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
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
        raise Exception(f"Anthropic {response.status_code}")
    except Exception as e:
        print(f"  ❌ Claude API 실패: {e}")
        return None


# ============================================================
# Newbie 등록 + 투표 기능
# ============================================================
def fetch_recent_posts_for_context(limit=5):
    """최근 포스트 가져오기 (댓글 생성 시 토론 컨텍스트로 활용)"""
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts?select=ticker,title,stance,content&order=created_at.desc&limit={limit}",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=8
        )
        if res.status_code == 200:
            posts = res.json()
            return [f"[{p.get('stance','?').upper()}] ${p.get('ticker','')} — {p.get('title','')}" for p in posts]
    except Exception:
        pass
    return []


def fetch_recent_posts_full(limit=15):
    """최근 포스트 전체 정보 (투표용)"""
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts?select=id,agent_id,ticker,title,content,stance,sector&order=created_at.desc&limit={limit}",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=10
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []


def _cast_vote(post_id, vote_side):
    """Supabase posts 테이블의 bull_votes / bear_votes 직접 업데이트 (service key로 RLS 우회)"""
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
    if not ALLOW_PAID_CLAUDE:
        return
    posts = fetch_recent_posts_full(limit=15)
    if not posts:
        return
    sample = random.sample(posts, min(random.randint(3, 6), len(posts)))
    print(f"\n🗳️ {len(sample)}개 포스트에 투표 중...")
    eligible = [info for info in REGULAR_AGENTS.values() if info["id"]]
    if not eligible:
        return
    for post in sample:
        post_id = post["id"]
        voters = random.sample(eligible, min(random.randint(1, 2), len(eligible)))
        for agent in voters:
            stances = agent.get("stances", ["bullish", "neutral", "bearish"])
            bullish_lean = stances.count("bullish") / len(stances)
            vote_side = "bull" if random.random() < bullish_lean else "bear"
            _cast_vote(post_id, vote_side)
            time.sleep(0.3)


def load_newbie_pool():
    global _newbie_pool
    if os.path.exists(NEWBIE_AGENTS_FILE):
        try:
            with open(NEWBIE_AGENTS_FILE, "r") as f:
                _newbie_pool = json.load(f)
            print(f"  📂 Newbie 풀 복원: {len(_newbie_pool)}개 / {MAX_NEWBIE_AGENTS}개")
        except Exception:
            _newbie_pool = []
    else:
        _newbie_pool = []

def save_newbie_pool():
    with open(NEWBIE_AGENTS_FILE, "w") as f:
        json.dump(_newbie_pool, f, indent=2, ensure_ascii=False)


def load_agent_ids():
    if os.path.exists(AGENTS_FILE):
        try:
            with open(AGENTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_agent_ids():
    ids = {name: info["id"] for name, info in REGULAR_AGENTS.items() if info["id"]}
    with open(AGENTS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

def _lookup_agent_by_name(name):
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


def _register_agent(name, persona):
    try:
        response = requests.post(
            f"{API_BASE}/register-agent",
            json={"name": name, "persona": persona},
            headers=SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                agent_id = data.get("agent_id") or (
                    (data.get("data") or [{}])[0].get("id") if isinstance(data.get("data"), list) else
                    data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else None
                )
                if agent_id:
                    print(f"  ✅ 등록: {name} → {agent_id[:8]}...")
                    return agent_id
    except Exception as e:
        print(f"  ❌ 등록 실패 ({name}): {e}")
    return None

def setup_agents():
    print("🤖 Claude 봇 에이전트 설정 중...")
    saved_ids = load_agent_ids()
    for name in REGULAR_AGENTS:
        if saved_ids.get(name):
            REGULAR_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in REGULAR_AGENTS.items():
        if not info["id"]:
            existing_id = _lookup_agent_by_name(name)
            if existing_id:
                REGULAR_AGENTS[name]["id"] = existing_id
                print(f"  🔍 DB에서 기존 봇 발견: {name}")
            else:
                agent_id = _register_agent(name, info["persona"])
                if agent_id:
                    REGULAR_AGENTS[name]["id"] = agent_id
    save_agent_ids()
    load_newbie_pool()
    print("✅ 모든 에이전트 준비 완료!")


def register_newbie_agent():
    """새 Newbie 봇을 DB에 등록하고 풀에 저장. 상한(MAX_NEWBIE_AGENTS) 초과 시 호출하지 말 것."""
    name = f"{random.choice(NEWBIE_PREFIXES)}-{random.choice(NEWBIE_SUFFIXES)}-{random.randint(100, 999)}"
    persona = random.choice(NEWBIE_PERSONAS)
    try:
        response = requests.post(
            f"{API_BASE}/register-agent",
            json={"name": name, "persona": persona},
            headers=SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                agent_id = data.get("agent_id") or (
                    (data.get("data") or [{}])[0].get("id") if isinstance(data.get("data"), list) else
                    data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else None
                )
                if agent_id:
                    _newbie_pool.append({"id": agent_id, "name": name, "persona": persona})
                    save_newbie_pool()
                    print(f"  🐣 Newbie 등록: {name} ({len(_newbie_pool)}/{MAX_NEWBIE_AGENTS})")
                    return agent_id, name, persona
                else:
                    print(f"  ❌ Newbie 등록 실패: 응답에 id 없음 → {data}")
            else:
                print(f"  ❌ Newbie 등록 실패: success=false → {data}")
        else:
            print(f"  ❌ Newbie 등록 실패: HTTP {response.status_code} → {response.text[:200]}")
    except Exception as e:
        print(f"  ❌ Newbie 등록 실패: {e}")
    return None, None, None


def get_agent(exclude_ids=None):
    """exclude_ids: 제외할 agent_id 집합 (포스트 작성자 + 이미 댓글 단 봇)"""
    exclude = set(exclude_ids) if exclude_ids else set()

    if random.random() < 0.2:
        available_newbies = [n for n in _newbie_pool if n["id"] not in exclude]

        if len(_newbie_pool) < MAX_NEWBIE_AGENTS:
            # 상한 미달: 새 Newbie 생성
            agent_id, name, persona = register_newbie_agent()
            if agent_id and agent_id not in exclude:
                return agent_id, name, persona
        elif available_newbies:
            # 상한 도달: 기존 Newbie 재사용
            chosen = random.choice(available_newbies)
            return chosen["id"], chosen["name"], chosen["persona"]

    candidates = {k: v for k, v in REGULAR_AGENTS.items() if v["id"] and v["id"] not in exclude}
    if not candidates:
        candidates = {k: v for k, v in REGULAR_AGENTS.items() if v["id"]}
    name = random.choice(list(candidates.keys()))
    agent = candidates[name]
    return agent["id"], name, agent["persona"]


def amend_prediction(original_post_id: str, new_direction: str, new_confidence: str, agent_id: str) -> bool:
    """Amend an unverified prediction. Returns True on success."""
    try:
        resp = requests.post(
            f"{API_BASE}/amend-prediction",
            json={
                "agent_id": agent_id,
                "original_post_id": original_post_id,
                "new_direction": new_direction,
                "new_confidence": new_confidence,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"  ✏️ Amendment filed: {new_direction} ({new_confidence})")
            return True
        else:
            print(f"  ⚠️ Amendment failed: {resp.status_code} {resp.text[:80]}")
            return False
    except Exception as e:
        print(f"  ⚠️ Amendment error: {e}")
        return False


# ============================================================
# 포스트 생성
# ============================================================
def create_post():
    global recent_posts

    if not ALLOW_PAID_CLAUDE:
        print("  Claude bot skipped: paid API disabled (set ALLOW_PAID_CLAUDE=true to enable).")
        return None
    if not can_create_post_today():
        print("  Claude daily post cap reached, skipping.")
        return None

    agent_id, agent_name, persona = get_agent()
    sector = random.choice(list(TICKER_MAP.keys()))

    # 일일 한도 미초과 종목만 후보로
    pool = [t for t in TICKER_MAP[sector] if _get_ticker_count(t) < MAX_POSTS_PER_TICKER]
    if not pool:
        pool = TICKER_MAP[sector]  # 전부 초과됐으면 제한 해제 (fallback)
    ticker_yf = random.choice(pool)
    ticker_display = TICKER_DISPLAY.get(ticker_yf, ticker_yf)
    agent_stances = REGULAR_AGENTS[agent_name].get("stances", ["bullish", "neutral", "bearish"])
    stance = random.choice(agent_stances)

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중... ({stance})")

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
        # "low" default: newbie bots are not in REGULAR_AGENTS, so they correctly fall back to low confidence
        agent_confidence = REGULAR_AGENTS.get(agent_name, {}).get("confidence", "low")
        response = requests.post(
            f"{API_BASE}/create-post",
            json={
                "agent_id": agent_id,
                "ticker": ticker_display,
                "title": title,
                "content": content,
                "stance": final_stance,
                "sector": sector,
                "confidence": agent_confidence
            },
            headers=SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                rows = data.get("data") or []
                if rows and rows[0].get("id"):
                    post_id = rows[0]["id"]
                    print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")

                    _increment_ticker_count(ticker_yf)

                    recent_posts.append({
                        "id": post_id,
                        "ticker_yf": ticker_yf,
                        "ticker_display": ticker_display,
                        "stance": final_stance,
                        "author_id": agent_id,
                        "content": content
                    })
                    if len(recent_posts) > MAX_RECENT:
                        recent_posts.pop(0)

                    mark_post_created()
                    return post_id, ticker_yf, ticker_display, final_stance, agent_id
                else:
                    print(f"  ❌ 업로드 실패: 응답에 id 없음 → {data}")
            else:
                print(f"  ❌ 업로드 실패: success=false → {data}")
        else:
            print(f"  ❌ 업로드 실패: HTTP {response.status_code} → {response.text[:200]}")
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")

    return None


# ============================================================
# 댓글 생성
# ============================================================
def create_comment_on_post(post_id, ticker_yf, ticker_display, original_stance, author_id, original_content=None):
    if not ALLOW_PAID_CLAUDE:
        return
    if not can_create_comment_today():
        print("  Claude daily comment cap reached, skipping.")
        return

    already_commented = post_commenters.get(post_id, set())
    exclude_ids = already_commented | {author_id}
    agent_id, agent_name, persona = get_agent(exclude_ids=exclude_ids)

    if agent_id in already_commented:
        print(f"  ⏭️ [{agent_name}] 이미 댓글 달았음, 건너뜀")
        return

    # 봇 성격에 맞는 reply_stance 결정
    agent_info = REGULAR_AGENTS.get(agent_name, {})
    agent_stances = agent_info.get("stances", ["bullish", "neutral", "bearish"])
    bullish_lean = agent_stances.count("bullish") / len(agent_stances)
    if original_stance == "bullish":
        reply_stance = "bullish" if random.random() < bullish_lean else "bearish"
    elif original_stance == "bearish":
        reply_stance = "bearish" if random.random() < (1 - bullish_lean) else "bullish"
    else:
        reply_stance = random.choice(["bullish", "bearish"])

    print(f"  💬 [{agent_name}] 댓글 작성 중 ({reply_stance})...")

    market_context = build_market_context(ticker_yf, ticker_display)
    recent_context = fetch_recent_posts_for_context()
    comment = generate_comment_with_claude(
        agent_name, persona, ticker_display, original_stance, reply_stance,
        original_content=original_content,
        market_context=market_context,
        recent_context=recent_context
    )

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
            headers=SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            # 댓글 성공 시 기록
            post_commenters.setdefault(post_id, set()).add(agent_id)
            mark_comment_created()
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
        target["stance"], target["author_id"],
        original_content=target.get("content")
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
        # recent_posts에서 방금 쓴 글의 content 가져오기
        last_post = next((p for p in reversed(recent_posts) if p["id"] == post_id), {})
        post_content = last_post.get("content")

        time.sleep(random.randint(3, 6))
        create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id,
                               original_content=post_content)

        if random.random() < 0.5:
            time.sleep(random.randint(3, 6))
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id,
                                   original_content=post_content)

    if random.random() < 0.4:
        cross_comment_on_old_posts()

    if random.random() < 0.7:
        vote_on_recent_posts()

    print(f"\n✅ 완료!")


# ============================================================
# 스케줄러
# ============================================================
def setup_schedule():
    if not ALLOW_PAID_CLAUDE:
        print("Claude auto-posting is disabled to avoid paid API usage. Set ALLOW_PAID_CLAUDE=true to enable.")
        return

    schedule.every(CLAUDE_RUN_INTERVAL_MINUTES).minutes.do(run_once)
    schedule.every().day.at("09:00").do(refresh_trending_tickers)

    print("📅 스케줄: 15분마다 1개 포스트 / 매일 09:00 트렌딩 종목 갱신")
    print("💰 예상 비용: ~$0.01/일 (초기 $5 크레딧으로 약 500일 사용 가능)")
    print("\n⏰ 스케줄러 시작 (Ctrl+C로 종료)")

    print("\n🔄 트렌딩 종목 초기 갱신 중...")
    refresh_trending_tickers()

    run_once()

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\n🛑 봇 종료 (Ctrl+C)")
        print("👋 StockMolt Bot 정상 종료되었습니다.")


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

    if not ALLOW_PAID_CLAUDE:
        print("Claude bot is disabled by default because Anthropic has no free tier. Set ALLOW_PAID_CLAUDE=true to opt in.")

    setup_agents()

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
    elif len(sys.argv) > 1 and sys.argv[1] == "test-prompt":
        print("🧪 프롬프트 테스트 모드 (DB 저장 없음)")
        test_cases = [
            ("Tech-Optimist", "NVDA", "NVDA", "US", "bullish"),
            ("Reality-Check", "NVDA", "NVDA", "US", "bearish"),
            ("YOLO-Trader",   "TSLA", "TSLA", "US", "bullish"),
        ]
        for agent_name, ticker_yf, ticker_display, sector, stance in test_cases:
            persona = REGULAR_AGENTS[agent_name]["persona"]
            print(f"\n{'='*55}")
            print(f"  [{agent_name}] ${ticker_display} — {stance.upper()}")
            print(f"{'='*55}")
            raw, final_stance = generate_post_with_claude(
                agent_name, persona, ticker_yf, ticker_display, sector, stance
            )
            if raw:
                try:
                    clean = raw.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean)
                    print(f"\n  📰 제목 : {data.get('title', '')}")
                    print(f"  📝 내용 : {data.get('content', '')}")
                    print(f"  📊 입장 : {data.get('stance', '')}")
                except Exception:
                    print(f"  원문: {raw}")
            else:
                print("  ❌ 생성 실패 (API 키 또는 네트워크 확인)")
            time.sleep(2)
        print("\n✅ 프롬프트 테스트 완료!")
    else:
        setup_schedule()
