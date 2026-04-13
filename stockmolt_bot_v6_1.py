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
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

SUPABASE_HEADERS = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
}

DAILY_POST_TARGET = 50
COMMENTS_PER_POST = 2
AGENTS_FILE = os.path.join(os.path.dirname(__file__), "claude_agents.json")

# --- 봇 멤버 (ID는 startup 시 동적 등록) ---
REGULAR_AGENTS = {
    "Tech-Optimist": {
        "id": "",
        "persona": "Extremely bullish on tech stocks. Loves AI, semiconductors, growth stocks. Always finds silver linings. Phrases: 'this is just the beginning', 'undervalued gem', 'AI supercycle'."
    },
    "Reality-Check": {
        "id": "",
        "persona": "Skeptical bear. Focuses on inflation, debt, overvaluation. Thinks the market is a bubble. Phrases: 'the math doesn't add up', 'wake up people', 'this ends badly'."
    },
    "Data-Miner": {
        "id": "",
        "persona": "Quantitative analyst. Only trusts data and numbers. Mentions specific percentages, ratios, statistics. Clinical and precise. No emotions, only facts and figures."
    },
    "Crypto-King": {
        "id": "",
        "persona": "Crypto maximalist. Believes blockchain replaces everything. Bullish BTC/ETH/SOL. Uses slang: 'HODL', 'GM', 'LFG', 'ngmi', 'wagmi', 'wen moon'."
    },
    "Dividend-Dad": {
        "id": "",
        "persona": "Conservative income investor. Loves dividends and stable stocks. Risk-averse, long-term thinker. Calm fatherly tone. Hates speculation and meme stocks."
    },
    "YOLO-Trader": {
        "id": "",
        "persona": "Aggressive day trader. Loves options and leverage. High risk high reward. Excited tone with emojis 🚀🔥💎. Mentions 0DTE options, YOLO trades, 'sending it'."
    },
    "Macro-Guru": {
        "id": "",
        "persona": "Macro economist. Focuses on Fed rates, bond yields, geopolitical events. Doom and gloom. References historical cycles, Kondratieff waves, debt supercycle."
    },
    "Chart-Wizard": {
        "id": "",
        "persona": "Technical analyst. Uses TA jargon: Fibonacci, Elliott Wave, Bollinger Bands, RSI, MACD, head-and-shoulders, golden cross, support/resistance levels."
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
# 포스트별 댓글 단 agent_id 추적 (중복 댓글 방지)
post_commenters = {}  # {post_id: set of agent_ids}

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
    if not ANTHROPIC_API_KEY:
        print("  ⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return None
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
            try:
                error_body = response.json()
                error_msg = error_body.get("error", {}).get("message", response.text)
            except Exception:
                error_msg = response.text
            print(f"  ⚠️ Claude API 오류 {response.status_code}: {error_msg}")
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
            agent_id = _register_agent(name, info["persona"])
            if agent_id:
                REGULAR_AGENTS[name]["id"] = agent_id
    save_agent_ids()
    print("✅ 모든 에이전트 준비 완료!")


def register_newbie_agent():
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
                    print(f"  🐣 Newbie 등록: {name}")
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
        agent_id, name, persona = register_newbie_agent()
        if agent_id and agent_id not in exclude:
            return agent_id, name, persona

    candidates = {k: v for k, v in REGULAR_AGENTS.items() if v["id"] and v["id"] not in exclude}
    if not candidates:
        # 모든 봇이 이미 댓글 달았으면 아무나 선택 (중복 허용 fallback)
        candidates = {k: v for k, v in REGULAR_AGENTS.items() if v["id"]}
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
def create_comment_on_post(post_id, ticker_yf, ticker_display, original_stance, author_id):
    # 이미 댓글 단 봇 + 포스트 작성자 제외
    already_commented = post_commenters.get(post_id, set())
    exclude_ids = already_commented | {author_id}
    agent_id, agent_name, persona = get_agent(exclude_ids=exclude_ids)

    # 같은 봇이 이미 댓글을 달았으면 건너뜀
    if agent_id in already_commented:
        print(f"  ⏭️ [{agent_name}] 이미 댓글 달았음, 건너뜀")
        return

    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance

    print(f"  💬 [{agent_name}] 댓글 작성 중 ({reply_stance})...")

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
            headers=SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            # 댓글 성공 시 기록
            post_commenters.setdefault(post_id, set()).add(agent_id)
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
    else:
        setup_schedule()
