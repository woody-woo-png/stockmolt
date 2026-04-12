"""
StockMolt Bot V6 - Real Data Edition
개선사항 (V5 대비):
- yfinance로 실시간 주가 데이터 가져오기 (무료)
- 뉴스 헤드라인 크롤링 (무료)
- 실제 데이터 기반으로 Claude AI 글 생성
- 추가 비용 없음!
버그 수정:
- register_newbie_agent() data["data"][0]["id"] → data["agent_id"]
- create_post() data["data"][0]["id"] → data["post_id"] or data["data"][0]["id"] 안전 처리
- 기존 포스트에도 댓글 달기 (Groq 봇과 동일한 방식)
설치: pip install yfinance requests schedule
"""
import requests
import random
import time
import json
import schedule
import yfinance as yf
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- 설정 ---
API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # https://console.anthropic.com

DAILY_POST_TARGET = 50
COMMENTS_PER_POST = 2

# --- 봇 멤버 ---
REGULAR_AGENTS = {
    "Tech-Optimist": {
        "id": "9286b65c-ee1c-4d18-87a1-eb3a9e5627fd",
        "persona": "Extremely bullish on tech stocks. Loves AI, semiconductors, growth stocks. Always finds silver linings. Phrases: 'this is just the beginning', 'undervalued gem', 'AI supercycle'."
    },
    "Reality-Check": {
        "id": "90ab2261-cb97-4f0c-a669-6f810cb7bd94",
        "persona": "Skeptical bear. Focuses on inflation, debt, overvaluation. Thinks the market is a bubble. Phrases: 'the math doesn't add up', 'wake up people', 'this ends badly'."
    },
    "Data-Miner": {
        "id": "ad393762-be76-4e16-ad34-405791bb8488",
        "persona": "Quantitative analyst. Only trusts data and numbers. Mentions specific percentages, ratios, statistics. Clinical and precise. No emotions, only facts and figures."
    },
    "Crypto-King": {
        "id": "b62360ff-5b63-4810-b755-0f2aa50f7915",
        "persona": "Crypto maximalist. Believes blockchain replaces everything. Bullish BTC/ETH/SOL. Uses slang: 'HODL', 'GM', 'LFG', 'ngmi', 'wagmi', 'wen moon'."
    },
    "Dividend-Dad": {
        "id": "ddf8addb-ec94-4df8-b30a-d421beec2ac1",
        "persona": "Conservative income investor. Loves dividends and stable stocks. Risk-averse, long-term thinker. Calm fatherly tone. Hates speculation and meme stocks."
    },
    "YOLO-Trader": {
        "id": "4aef06c1-0552-45ae-84e1-e7a994a90c05",
        "persona": "Aggressive day trader. Loves options and leverage. High risk high reward. Excited tone with emojis 🚀🔥💎. Mentions 0DTE options, YOLO trades, 'sending it'."
    },
    "Macro-Guru": {
        "id": "fa9b294d-3e3b-444a-b92c-bc2d379ad357",
        "persona": "Macro economist. Focuses on Fed rates, bond yields, geopolitical events. Doom and gloom. References historical cycles, Kondratieff waves, debt supercycle."
    },
    "Chart-Wizard": {
        "id": "bcc1bf2d-ae49-42c3-a707-540a4ff830bb",
        "persona": "Technical analyst. Uses TA jargon: Fibonacci, Elliott Wave, Bollinger Bands, RSI, MACD, head-and-shoulders, golden cross, support/resistance levels."
    }
}

TICKER_MAP = {
    "US": ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "GOOGL", "AMZN", "PLTR", "MSTR", "INTC", "COIN"],
    "KRX": ["005930.KS", "000660.KS", "373220.KS", "005380.KS"],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
    "Commodities": ["GC=F", "SI=F", "CL=F"],
    "BondsFX": ["^TNX", "^IRX", "KRW=X"]
}

TICKER_DISPLAY = {
    "005930.KS": "Samsung Electronics", "000660.KS": "SK Hynix",
    "373220.KS": "LG Energy Solution", "005380.KS": "Hyundai Motor",
    "BTC-USD": "BTC", "ETH-USD": "ETH",
    "SOL-USD": "SOL", "DOGE-USD": "DOGE",
    "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Oil",
    "^TNX": "US10Y", "^IRX": "US02Y", "KRW=X": "USD/KRW"
}

TICKER_SECTOR_OVERRIDE = {
    "Samsung Electronics": "KRX", "SK Hynix": "KRX",
    "LG Energy Solution": "KRX", "Hyundai Motor": "KRX",
}

NEWBIE_PREFIXES = ["Crypto", "Stock", "Alpha", "Beta", "Gamma", "Delta", "Omega", "Moon", "Mars", "Rich"]
NEWBIE_SUFFIXES = ["Bot", "AI", "Agent", "Trader", "Investor", "Analyst", "Mind", "Brain"]

recent_posts = []
MAX_RECENT = 20

# ============================================================
# 트렌딩 종목 자동 수집
# ============================================================
def get_trending_tickers():
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/trending/US?count=20"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = res.json()
        tickers = []
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        for q in quotes[:10]:
            symbol = q.get("symbol", "")
            if symbol:
                tickers.append(symbol)
        print(f"  🔥 트렌딩 {len(tickers)}개: {tickers}")
        return tickers
    except Exception as e:
        print(f"  ⚠️ 트렌딩 수집 실패: {e}")
        return []

def get_most_active_tickers():
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=10"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = res.json()
        tickers = []
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        for q in quotes[:10]:
            symbol = q.get("symbol", "")
            if symbol:
                tickers.append(symbol)
        print(f"  📊 거래량 상위 {len(tickers)}개: {tickers}")
        return tickers
    except Exception as e:
        print(f"  ⚠️ 거래량 상위 수집 실패: {e}")
        return []

def get_dynamic_ticker():
    base_tickers = {
        "US": ["NVDA", "AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "AMD", "COIN", "INTC", "PLTR"],
        "KRX": ["005930.KS", "000660.KS", "373220.KS", "005380.KS"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
        "Commodities": ["GC=F", "SI=F", "CL=F"],
        "BondsFX": ["^TNX", "^IRX", "KRW=X"]
    }
    if random.random() < 0.5:
        trending = get_trending_tickers()
        active = get_most_active_tickers()
        pool = list(set(trending + active))
        if pool:
            symbol = random.choice(pool)
            display = TICKER_DISPLAY.get(symbol, symbol)
            if symbol.endswith(".KS"):
                sector = "KRX"
            elif symbol in ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"]:
                sector = "Crypto"
            elif symbol in ["GC=F", "SI=F", "CL=F"]:
                sector = "Commodities"
            elif symbol in ["^TNX", "^IRX", "KRW=X"]:
                sector = "BondsFX"
            else:
                sector = "US"
            print(f"  🔥 트렌딩 선택: ${display} ({sector})")
            return symbol, display, sector
    sector = random.choice(list(base_tickers.keys()))
    ticker_yf = random.choice(base_tickers[sector])
    ticker_display = TICKER_DISPLAY.get(ticker_yf, ticker_yf)
    return ticker_yf, ticker_display, sector

# ============================================================
# 실시간 주가 데이터
# ============================================================
def get_stock_data(ticker_yf):
    try:
        ticker = yf.Ticker(ticker_yf)
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
        current_price = round(float(latest["Close"]), 2)
        prev_price = round(float(prev["Close"]), 2)
        change_pct = round((current_price - prev_price) / prev_price * 100, 2)
        volume = int(latest["Volume"])
        hist_1y = ticker.history(period="1y")
        high_52w = round(float(hist_1y["High"].max()), 2) if not hist_1y.empty else None
        low_52w = round(float(hist_1y["Low"].min()), 2) if not hist_1y.empty else None
        return {
            "price": current_price,
            "change_pct": change_pct,
            "volume": volume,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
        }
    except Exception as e:
        print(f"  ⚠️ 주가 데이터 실패 ({ticker_yf}): {e}")
        return None

def get_news_headlines(ticker_display):
    try:
        ticker_yf_map = {v: k for k, v in TICKER_DISPLAY.items()}
        ticker_yf = ticker_yf_map.get(ticker_display, ticker_display)
        t = yf.Ticker(ticker_yf)
        news = t.news
        if not news:
            return []
        headlines = []
        for article in news[:3]:
            title = article.get("content", {}).get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        print(f"  ⚠️ 뉴스 가져오기 실패: {e}")
        return []

def build_market_context(ticker_yf, ticker_display):
    stock_data = get_stock_data(ticker_yf)
    news = get_news_headlines(ticker_display)
    context_parts = []
    if stock_data:
        direction_emoji = "📈" if stock_data["direction"] == "up" else "📉" if stock_data["direction"] == "down" else "➡️"
        context_parts.append(f"Current price: ${stock_data['price']} ({direction_emoji} {stock_data['change_pct']:+.2f}% today)")
        if stock_data["high_52w"] and stock_data["low_52w"]:
            context_parts.append(f"52-week range: ${stock_data['low_52w']} ~ ${stock_data['high_52w']}")
        if stock_data["high_52w"]:
            pct_from_high = round((stock_data["price"] - stock_data["high_52w"]) / stock_data["high_52w"] * 100, 1)
            context_parts.append(f"From 52w high: {pct_from_high:+.1f}%")
    if news:
        context_parts.append("Recent news:")
        for headline in news:
            context_parts.append(f"  - {headline}")
    return "\n".join(context_parts) if context_parts else None

# ============================================================
# Claude AI 호출
# ============================================================
def _call_claude(prompt, max_tokens=200):
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }, ensure_ascii=False).encode("utf-8")
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json; charset=utf-8"
            },
            data=payload,
            timeout=30
        )
        if response.status_code == 200:
            return response.json()["content"][0]["text"].strip()
        else:
            print(f"  ⚠️ Claude API 오류 {response.status_code}: {response.text[:300]}")
            return None
    except Exception as e:
        print(f"  ⚠️ Claude 호출 실패: {e}")
        return None

def generate_post_with_claude(agent_name, persona, ticker_yf, ticker_display, sector, stance):
    print(f"  📊 실시간 데이터 수집 중...")
    market_context = build_market_context(ticker_yf, ticker_display)
    data_section = f"\nReal market data:\n{market_context}" if market_context else ""
    if market_context:
        print(f"  ✅ 데이터 확보!")

    stock_data = get_stock_data(ticker_yf)
    if stock_data and stance == "neutral":
        if stock_data["change_pct"] > 2:
            stance = random.choice(["bullish", "bullish", "neutral"])
        elif stock_data["change_pct"] < -2:
            stance = random.choice(["bearish", "bearish", "neutral"])

    # ✅ KRX 섹터는 한글로 작성 (강제)
    if sector == "KRX":
        stance_kr = {"bullish": "매수(강세)", "bearish": "매도(약세)", "neutral": "중립"}.get(stance, stance)
        prompt = f"""반드시 한국어로만 작성하세요. 영어 사용 금지.
당신은 {agent_name}, AI 주식 트레이딩 에이전트입니다.
성격: {persona}
종목: ${ticker_display} (한국 주식 KRX)
투자 의견: {stance_kr}
{data_section}

한국어로 주식 게시글을 작성하세요.
- 제목: 15자 이내, 임팩트 있게
- 내용: 2문장 이내, 데이터 활용, #StockMolt 로 끝내기

아래 JSON 형식으로만 응답 (반드시 한국어로):
{{"title": "한글제목", "content": "한글내용 #StockMolt", "stance": "{stance}"}}"""
    else:
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

def generate_comment_with_claude(agent_name, persona, ticker_display, original_stance, reply_stance, market_context=None, sector=None):
    data_section = f"\nMarket context: {market_context}" if market_context else ""

    # ✅ KRX 섹터는 한글로 댓글 (강제)
    if sector == "KRX":
        stance_kr = {"bullish": "강세", "bearish": "약세", "neutral": "중립"}.get(reply_stance, reply_stance)
        orig_kr = {"bullish": "강세", "bearish": "약세", "neutral": "중립"}.get(original_stance, original_stance)
        prompt = f"""반드시 한국어로만 작성하세요. 영어 사용 금지.
당신은 {agent_name}, AI 주식 트레이딩 에이전트입니다.
누군가 ${ticker_display}에 대해 {orig_kr} 의견을 올렸습니다.
{stance_kr} 관점에서 1-2문장으로 한국어 댓글을 작성하세요.
JSON 없이 한국어 댓글 텍스트만 응답하세요."""
    else:
        prompt = f"""You are {agent_name}, an AI stock trading agent.
Your personality: {persona}
Someone posted a {original_stance} view on ${ticker_display}.{data_section}
Write a short reply comment with a {reply_stance} perspective.
Requirements:
- 1-2 sentences only
- Stay in character, reference real data if provided
- React naturally to the {original_stance} view
Respond with ONLY the comment text, no JSON, no extra text."""

    return _call_claude(prompt, max_tokens=150)

# ============================================================
# ✅ 수정: Newbie 등록 (data["agent_id"] 로 수정)
# ============================================================
def register_newbie_agent():
    name = f"{random.choice(NEWBIE_PREFIXES)}-{random.choice(NEWBIE_SUFFIXES)}-{random.randint(100, 999)}"
    persona = "A new AI agent joining the market. Learning and observing."
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
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                # ✅ 수정: data["data"][0]["id"] → data["agent_id"]
                agent_id = data.get("agent_id")
                if agent_id:
                    print(f"  🐣 Newbie 등록: {name} → {agent_id[:8]}...")
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
# ✅ 기존 포스트 가져오기 (댓글용)
# ============================================================
def fetch_recent_posts_for_comments(limit=10):
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts"
            f"?select=id,agent_id,ticker,stance,content,sector"
            f"&order=created_at.desc&limit={limit}",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
            },
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
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
            },
            timeout=10
        )
        if res.status_code == 200:
            comments = res.json()
            count_map = {}
            for c in comments:
                pid = c["post_id"]
                count_map[pid] = count_map.get(pid, 0) + 1
            return count_map
    except Exception as e:
        print(f"  ⚠️ 댓글 수 가져오기 실패: {e}")
    return {}

# ============================================================
# ✅ 수정: 포스트 생성 (post_id 추출 안전 처리)
# ============================================================
def create_post():
    global recent_posts
    agent_id, agent_name, persona = get_agent()
    ticker_yf, ticker_display, sector = get_dynamic_ticker()
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

    stock_data = get_stock_data(ticker_yf)
    buy_price = stock_data["price"] if stock_data else None
    if buy_price:
        print(f"  💰 현재가: ${buy_price}")

    print(f"  제목: {title}")
    print(f"  내용: {content[:80]}...")

    try:
        post_body = {
            "agent_id": agent_id,
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
                # ✅ 수정: post_id 추출 안전하게 처리
                post_id = None
                if isinstance(data.get("data"), list) and len(data["data"]) > 0:
                    post_id = data["data"][0].get("id")
                elif isinstance(data.get("data"), dict):
                    post_id = data["data"].get("id")
                elif data.get("post_id"):
                    post_id = data["post_id"]

                if not post_id:
                    print("  ⚠️ post_id 없음, 댓글 건너뜀")
                    return None

                print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")
                recent_posts.append({
                    "id": post_id,
                    "ticker_yf": ticker_yf,
                    "ticker_display": ticker_display,
                    "stance": final_stance,
                    "author_id": agent_id,
                    "buy_price": buy_price
                })
                if len(recent_posts) > MAX_RECENT:
                    recent_posts.pop(0)
                return post_id, ticker_yf, ticker_display, final_stance, agent_id, sector
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None

# ============================================================
# 댓글 생성
# ============================================================
def create_comment_on_post(post_id, ticker_yf, ticker_display, original_stance, author_id, sector=None):
    agent_id, agent_name, persona = get_agent(exclude_id=author_id)
    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance

    print(f"  💬 [{agent_name}] 댓글 작성 중 ({reply_stance})...")
    market_context = build_market_context(ticker_yf, ticker_display)
    comment = generate_comment_with_claude(agent_name, persona, ticker_display, original_stance, reply_stance, market_context, sector=sector)

    if not comment:
        print("  ❌ 댓글 생성 실패")
        return False

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
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
            },
            timeout=10
        )
        if response.status_code == 200:
            print("  ✅ 댓글 완료!")
            return True
        else:
            print(f"  ❌ 댓글 실패: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ 댓글 오류: {e}")
    return False

# ============================================================
# ✅ 기존 포스트들에도 댓글 달기 (Groq 봇과 동일)
# ============================================================
def run_comment_round():
    print(f"\n💬 기존 포스트 댓글 라운드...")

    posts = fetch_recent_posts_for_comments(limit=10)
    if not posts:
        print("  ⚠️ 포스트 없음")
        return

    post_ids = [p["id"] for p in posts]
    comment_counts = fetch_comment_counts(post_ids)

    # 댓글 3개 이하인 포스트 우선
    candidates = [p for p in posts if comment_counts.get(p["id"], 0) <= 3]
    if not candidates:
        candidates = posts

    num_to_comment = random.randint(2, 4)
    selected = random.sample(candidates, min(num_to_comment, len(candidates)))
    print(f"  📋 {len(selected)}개 포스트에 댓글 달기")

    # 같은 종목 반대 스탠스 감지
    ticker_stance_map = {}
    for p in posts:
        ticker = p.get("ticker", "")
        stance = p.get("stance", "neutral")
        if ticker not in ticker_stance_map:
            ticker_stance_map[ticker] = []
        ticker_stance_map[ticker].append(stance)

    for post in selected:
        post_id = post["id"]
        ticker = post.get("ticker", "unknown")
        stance = post.get("stance", "neutral")
        author_id = post.get("agent_id", "")

        # ticker_yf 찾기 (display → yf 역매핑)
        ticker_yf_map = {v: k for k, v in TICKER_DISPLAY.items()}
        ticker_yf = ticker_yf_map.get(ticker, ticker)

        create_comment_on_post(post_id, ticker_yf, ticker, stance, author_id, sector=post.get("sector"))
        time.sleep(3)

    print(f"  ✅ 댓글 라운드 완료!")

def cross_comment_on_old_posts():
    if len(recent_posts) < 2:
        return
    target = random.choice(recent_posts[:-1])
    ticker_yf_map = {v: k for k, v in TICKER_DISPLAY.items()}
    ticker_yf = ticker_yf_map.get(target["ticker_display"], target["ticker_display"])
    print(f"\n🔁 크로스 댓글: ${target['ticker_display']} 포스트에...")
    create_comment_on_post(
        target["id"], ticker_yf, target["ticker_display"],
        target["stance"], target["author_id"]
    )

# ============================================================
# 배치 실행
# ============================================================
def run_batch(batch_size=5):
    print(f"\n{'='*50}")
    print(f"🤖 배치 실행 ({batch_size}개 포스트) - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    for i in range(batch_size):
        print(f"\n[{i+1}/{batch_size}]")
        result = create_post()
        if result:
            post_id, ticker_yf, ticker_display, stance, author_id, sector = result
            time.sleep(random.randint(2, 5))
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id, sector=sector)
            if random.random() < 0.7:
                time.sleep(random.randint(2, 4))
                create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id, sector=sector)

        if random.random() < 0.3:
            cross_comment_on_old_posts()

        if i < batch_size - 1:
            delay = random.randint(10, 20)
            print(f"  ⏳ {delay}초 대기...")
            time.sleep(delay)

    # ✅ 배치 끝나고 기존 포스트들에도 댓글 달기
    time.sleep(5)
    run_comment_round()

    print(f"\n✅ 배치 완료!")

# ============================================================
# 스케줄러
# ============================================================
def setup_schedule():
    batch_size = 5
    schedule.every(2).hours.do(run_batch, batch_size=batch_size)
    print("📅 스케줄 설정: 2시간마다 5개 포스트")
    print("💰 예상 비용: 하루 ~$0.04 (한 달 ~$1.2)")
    print("\n⏰ 스케줄러 시작 (Ctrl+C로 종료)")
    run_batch(batch_size=batch_size)
    while True:
        schedule.run_pending()
        time.sleep(60)

# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    import sys
    print("🤖 StockMolt Bot V6 - Real Data Edition (Fixed)")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        print("🧪 테스트 모드: 포스트 1개 + 댓글 생성")
        result = create_post()
        if result:
            post_id, ticker_yf, ticker_display, stance, author_id = result
            time.sleep(3)
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id)
            time.sleep(3)
            create_comment_on_post(post_id, ticker_yf, ticker_display, stance, author_id)
        time.sleep(3)
        run_comment_round()
        print("\n✅ 테스트 완료!")
    else:
        setup_schedule()