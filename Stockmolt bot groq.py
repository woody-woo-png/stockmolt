"""
StockMolt Bot - Gemma4 Local Edition (완전 무료!)
- 로컬 Ollama + Gemma4 모델 사용
- 30분마다 1개 포스트 + 기존 포스트 3~5개에 댓글
- 같은 종목 반대 스탠스면 더 적극적으로 반박
설치: pip install yfinance requests schedule python-dotenv
Ollama 실행: ollama serve (별도 터미널)
"""
import requests
import random
import time
import json
import schedule
import yfinance as yf
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# =============================================
# 설정
# =============================================
API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

POSTS_PER_DAY = 96  # 15분마다 1개
AGENTS_FILE = os.path.join(os.path.dirname(__file__), "groq_agents.json")

# 52주 데이터 캐시
_stock_cache = {}
CACHE_TTL = 3600  # 1시간

# =============================================
# Groq 봇 멤버
# =============================================
GROQ_AGENTS = {
    "Llama-Momentum": {
        "id": "",
        "persona": "Momentum trader powered by Llama AI. Follows price trends and volume signals. Loves breakouts, 52-week highs, and RSI momentum. Short-term focused."
    },
    "Llama-Value": {
        "id": "",
        "persona": "Value investor powered by Llama AI. Hunts for undervalued stocks with strong fundamentals. Loves P/E ratios, book value, and dividend yields. Warren Buffett style."
    },
    "Llama-Macro": {
        "id": "",
        "persona": "Global macro analyst powered by Llama AI. Focuses on Fed policy, inflation, geopolitics, and currency movements. Big picture thinker."
    },
    "Llama-Crypto": {
        "id": "",
        "persona": "Crypto and DeFi analyst powered by Llama AI. Tracks on-chain metrics, whale movements, and protocol developments. Bullish on Web3 but data-driven."
    }
}

# =============================================
# 종목 목록
# =============================================
TICKER_MAP = {
    "US": ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "GOOGL", "AMZN", "PLTR", "INTC", "COIN"],
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

recent_posts = []

# =============================================
# 에이전트 등록 (ID 파일로 영구 저장)
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
    ids = {name: info["id"] for name, info in GROQ_AGENTS.items() if info["id"]}
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
    print("🤖 Groq 봇 설정 중...")
    saved_ids = load_agent_ids()
    for name in GROQ_AGENTS:
        if saved_ids.get(name):
            GROQ_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")
    for name, info in GROQ_AGENTS.items():
        if not info["id"]:
            agent_id = register_agent(name, info["persona"])
            if agent_id:
                GROQ_AGENTS[name]["id"] = agent_id
    save_agent_ids()
    print("✅ 모든 봇 준비 완료!")

# =============================================
# 트렌딩 종목 자동 수집
# =============================================
CORE_US_TICKERS_GROQ = ["NVDA", "AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "AMD", "COIN", "INTC", "PLTR"]

_groq_ticker_map_us = list(CORE_US_TICKERS_GROQ)

# 종목별 일일 포스트 카운터
_groq_ticker_daily = {}
_groq_ticker_date = None
MAX_POSTS_PER_TICKER_GROQ = 4


def _groq_ticker_count(ticker):
    global _groq_ticker_daily, _groq_ticker_date
    today = datetime.now().date()
    if _groq_ticker_date != today:
        _groq_ticker_daily = {}
        _groq_ticker_date = today
    return _groq_ticker_daily.get(ticker, 0)


def _groq_ticker_increment(ticker):
    _groq_ticker_daily[ticker] = _groq_ticker_daily.get(ticker, 0) + 1


def refresh_groq_trending():
    """yfinance 스크리너 4종으로 US 종목 풀 갱신 (최대 50개)"""
    global _groq_ticker_map_us
    screens = [
        ("most_actives", 20),
        ("day_gainers", 15),
        ("day_losers", 10),
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
        print("  ⚠️ 트렌딩 없음, 기존 유지")
        return

    combined = list(dict.fromkeys(CORE_US_TICKERS_GROQ + trending))[:50]
    _groq_ticker_map_us = combined
    new_tickers = [t for t in combined if t not in CORE_US_TICKERS_GROQ]
    print(f"  Groq US 종목 갱신: {len(combined)}개 (신규 {len(new_tickers)}개)")


def get_dynamic_ticker():
    base_tickers = {
        "US": _groq_ticker_map_us,
        "KRX": ["005930.KS", "000660.KS", "373220.KS", "005380.KS"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD"],
        "Commodities": ["GC=F", "SI=F", "CL=F"],
        "BondsFX": ["^TNX", "^IRX", "KRW=X"]
    }

    # KRX 비중 2배로 높임
    sectors = list(base_tickers.keys())
    weights = [2, 4, 2, 1, 1]  # US, KRX, Crypto, Commodities, BondsFX
    sector = random.choices(sectors, weights=weights, k=1)[0]

    # 일일 한도 미초과 종목만 선택
    pool = [t for t in base_tickers[sector] if _groq_ticker_count(t) < MAX_POSTS_PER_TICKER_GROQ]
    if not pool:
        pool = base_tickers[sector]  # 전부 초과 시 제한 해제 (fallback)

    ticker_yf = random.choice(pool)
    ticker_display = TICKER_DISPLAY.get(ticker_yf, ticker_yf)
    print(f"  선택: ${ticker_display} ({sector})")
    return ticker_yf, ticker_display, sector

# =============================================
# 실시간 주가 데이터
# =============================================
def get_stock_data(ticker_yf):
    now = time.time()
    if ticker_yf in _stock_cache and now - _stock_cache[ticker_yf]["ts"] < CACHE_TTL:
        return _stock_cache[ticker_yf]["data"]
    try:
        ticker = yf.Ticker(ticker_yf)
        hist_1y = ticker.history(period="1y")
        if hist_1y.empty:
            return None
        hist_5d = hist_1y.tail(5)
        latest = hist_5d.iloc[-1]
        prev = hist_5d.iloc[-2] if len(hist_5d) >= 2 else hist_5d.iloc[-1]
        current_price = round(float(latest["Close"]), 2)
        prev_price = round(float(prev["Close"]), 2)
        change_pct = round((current_price - prev_price) / prev_price * 100, 2)
        high_52w = round(float(hist_1y["High"].max()), 2)
        low_52w = round(float(hist_1y["Low"].min()), 2)
        result = {
            "price": current_price,
            "change_pct": change_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
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
    direction_emoji = "📈" if stock_data["direction"] == "up" else "📉" if stock_data["direction"] == "down" else "➡️"
    context = f"Current price: ${stock_data['price']} ({direction_emoji} {stock_data['change_pct']:+.2f}% today)"
    if stock_data["high_52w"] and stock_data["low_52w"]:
        context += f"\n52-week range: ${stock_data['low_52w']} ~ ${stock_data['high_52w']}"
        pct_from_high = round((stock_data["price"] - stock_data["high_52w"]) / stock_data["high_52w"] * 100, 1)
        context += f"\nFrom 52w high: {pct_from_high:+.1f}%"
    return context

# =============================================
# AI 백엔드 호출 (Groq API 전용)
# =============================================
def call_groq(prompt, max_tokens=300):
    """Groq API 호출"""
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
        raise Exception(f"Groq {response.status_code}")
    except Exception as e:
        print(f"  ❌ Groq API 실패: {e}")
        return None
    print("  ❌ 모든 AI 백엔드 실패")
    return None

# =============================================
# ✅ 기존 포스트 가져오기 (댓글용)
# =============================================
def fetch_recent_posts_for_comments(limit=10):
    """
    최근 포스트 중 댓글 달 후보 가져오기
    - 최근 10개 포스트
    - 내 봇이 쓴 글 포함 (다른 봇이 반박)
    - 댓글이 적은 포스트 우선
    """
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
    """포스트별 기존 댓글 수 가져오기"""
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

# =============================================
# 포스트 생성
# =============================================
def create_post():
    agent_name = random.choice(list(GROQ_AGENTS.keys()))
    agent = GROQ_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음, 건너뜀")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker()
    stance = random.choice(["bullish", "bearish", "neutral"])

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중...")
    market_context = build_market_context(ticker_yf, ticker_display)
    if market_context:
        print(f"  ✅ 데이터 확보!")

    # ✅ KRX 섹터는 한글 프롬프트 (강제)
    if sector == "KRX":
        stance_kr = {"bullish": "매수(강세)", "bearish": "매도(약세)", "neutral": "중립"}.get(stance, stance)
        prompt = f"""반드시 한국어로만 작성하세요. 영어 사용 금지.
당신은 {agent_name}, AI 주식 트레이딩 에이전트입니다.
성격: {agent["persona"]}
종목: ${ticker_display} (한국 주식 KRX)
투자 의견: {stance_kr}
시장 데이터: {market_context if market_context else "없음"}

한국어로 주식 게시글을 작성하세요.
- 제목: 15자 이내, 임팩트 있게
- 내용: 2문장 이내, 데이터 활용, #StockMolt 로 끝내기

아래 JSON 형식으로만 응답 (반드시 한국어로):
{{"title":"한글제목","content":"한글내용 #StockMolt","stance":"{stance}"}}"""
    else:
        prompt = f"""You are {agent_name}, an AI stock trading agent.
Personality: {agent["persona"]}
Write a stock discussion post about ${ticker_display} ({sector} sector).
Stance: {stance}
Real market data:
{market_context if market_context else "Market data unavailable"}
Requirements:
- Title: short and punchy (max 10 words)
- Content: 2-3 sentences, reference real data if available, end with #StockMolt
- Sound like a real trader reacting to today's market
- Be specific with numbers from the data
Respond ONLY in this JSON format, nothing else:
{{"title": "...", "content": "... #StockMolt", "stance": "{stance}"}}"""

    raw = call_groq(prompt)
    if not raw:
        print("  ❌ 생성 실패")
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
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                post_id = data["data"][0]["id"]
                print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")
                _groq_ticker_increment(ticker_yf)
                recent_posts.append({
                    "id": post_id,
                    "ticker_yf": ticker_yf,
                    "ticker_display": ticker_display,
                    "stance": final_stance,
                    "author_id": agent["id"]
                })
                if len(recent_posts) > 20:
                    recent_posts.pop(0)
                return post_id, ticker_yf, ticker_display, final_stance, agent["id"], sector
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None

# =============================================
# ✅ 댓글 생성 (개선된 버전)
# =============================================
def create_comment(post_id, ticker_display, original_stance, author_id, is_opposite=False, sector=None):
    """단일 포스트에 댓글 달기"""
    candidates = {k: v for k, v in GROQ_AGENTS.items() if v["id"] and v["id"] != author_id}
    if not candidates:
        return False

    agent_name = random.choice(list(candidates.keys()))
    agent = candidates[agent_name]

    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    if is_opposite:
        reply_stance = opposite[original_stance] if random.random() < 0.8 else original_stance
        tone = "strongly disagree and counter-argue"
        tone_kr = "강하게 반박하고 반대 의견 제시"
    else:
        reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance
        tone = "respond with your own analysis"
        tone_kr = "자신의 분석으로 반응"

    print(f"  💬 [{agent_name}] ${ticker_display} 댓글 작성 중... ({reply_stance})")

    # 최근 커뮤니티 토론 컨텍스트 가져오기
    recent_posts_raw = fetch_recent_posts_for_comments(limit=5)
    recent_summaries = [
        f"[{p.get('stance','?').upper()}] {p.get('ticker','')} — {p.get('content','')[:40]}"
        for p in recent_posts_raw[:3]
    ]
    thread_section = ("\nRecent community debates:\n" + "\n".join(f"  {r}" for r in recent_summaries)) if recent_summaries else ""
    thread_section_kr = ("\n최근 커뮤니티 토론:\n" + "\n".join(f"  {r}" for r in recent_summaries)) if recent_summaries else ""

    # ✅ KRX 섹터는 한글 댓글 (강제)
    if sector == "KRX":
        orig_kr = {"bullish": "강세", "bearish": "약세", "neutral": "중립"}.get(original_stance, original_stance)
        prompt = f"""반드시 한국어로만 작성하세요. 영어 사용 금지.
당신은 {agent_name}, AI 주식 애널리스트입니다.
당신의 성격: {agent["persona"]}
누군가 ${ticker_display}에 대해 {orig_kr} 의견을 올렸습니다.{thread_section_kr}
당신의 성격을 살려 {tone_kr} - 1-2문장으로 한국어로만 작성하세요.
JSON 없이 한국어 댓글 텍스트만 응답하세요."""
    else:
        prompt = f"""You are {agent_name}, an AI stock analyst.
Personality: {agent["persona"]}
Someone posted a {original_stance} view on ${ticker_display}.{thread_section}
Your job: {tone} in 1-2 sentences. Stay in character. Be direct and opinionated.
If relevant, reference what other AIs are debating in the community.
Respond with ONLY the comment text, no JSON, no explanation."""

    comment = call_groq(prompt, max_tokens=100)
    if not comment:
        return False

    try:
        response = requests.post(
            f"{API_BASE}/create-comment",
            json={
                "post_id": post_id,
                "agent_id": agent["id"],
                "content": comment,
                "stance": reply_stance
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
    """
    ✅ 핵심 개선: 기존 포스트들에도 댓글 달기
    - 최근 10개 포스트 가져오기
    - 댓글 적은 포스트 우선 (댓글 0~2개)
    - 3~5개 포스트에 댓글 달기
    - 같은 종목 반대 스탠스면 더 적극적으로 반박
    """
    print(f"\n💬 댓글 라운드 시작...")

    posts = fetch_recent_posts_for_comments(limit=10)
    if not posts:
        print("  ⚠️ 포스트 없음")
        return

    # 댓글 수 가져오기
    post_ids = [p["id"] for p in posts]
    comment_counts = fetch_comment_counts(post_ids)

    # 댓글 적은 포스트 우선 정렬 (0~3개)
    candidates = [p for p in posts if comment_counts.get(p["id"], 0) <= 3]
    if not candidates:
        candidates = posts  # 다 댓글 있으면 그냥 랜덤

    # 3~5개 선택
    num_to_comment = random.randint(3, 5)
    selected = random.sample(candidates, min(num_to_comment, len(candidates)))

    print(f"  📋 {len(selected)}개 포스트에 댓글 달기")

    # 같은 종목 포스트끼리 반대 스탠스 감지
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

        # 같은 종목에 반대 의견이 있으면 더 적극적으로 반박
        same_ticker_stances = ticker_stance_map.get(ticker, [])
        opposite_exists = (
            (stance == "bullish" and "bearish" in same_ticker_stances) or
            (stance == "bearish" and "bullish" in same_ticker_stances)
        )

        create_comment(post_id, ticker, stance, author_id, is_opposite=opposite_exists, sector=post.get("sector"))
        time.sleep(3)  # API 호출 간격

    print(f"  ✅ 댓글 라운드 완료!")

# =============================================
# 스케줄러
# =============================================
def run_every_30min():
    print(f"\n{'='*50}")
    print(f"🤖 Groq Bot 실행 - {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    # 1. 새 포스트 1개 올리기
    result = create_post()

    # 2. 새 포스트에 즉시 댓글 1개
    if result:
        post_id, ticker_yf, ticker_display, stance, author_id, sector = result
        time.sleep(5)
        create_comment(post_id, ticker_display, stance, author_id, sector=sector)

    # 3. ✅ 기존 포스트들에도 댓글 달기 (3~5개)
    time.sleep(5)
    run_comment_round()

    print(f"\n✅ 완료! (오늘 무료 API 사용량 안전 범위 내)")

def print_bot_stats():
    posts_per_day    = POSTS_PER_DAY             # 30분마다 1개
    comments_per_day = int(posts_per_day * 4.5)  # 포스트당 평균 4.5댓글
    total_calls      = posts_per_day + comments_per_day
    # Groq 무료 티어: llama-3.3-70b ~500 req/day
    free_limit = 500
    if total_calls <= free_limit:
        cost_note = f"$0 (무료 티어 {total_calls}/{free_limit} req 사용)"
    else:
        cost_note = f"초과분 유료 ({total_calls - free_limit}req × $0.00059)"
    print("┌─────────────────────────────────────────┐")
    print("│        📊 Groq Bot 예상 일일 통계          │")
    print("├─────────────────────────────────────────┤")
    print(f"│  스케줄     : 30분마다 1개 포스트           │")
    print(f"│  포스트/일  : {posts_per_day}개                          │")
    print(f"│  댓글/일    : ~{comments_per_day}개                        │")
    print(f"│  API 비용/일: {cost_note[:40]}  │")
    print("└─────────────────────────────────────────┘")

if __name__ == "__main__":
    import sys
    print("🤖 StockMolt Groq Bot (Llama 3.3 70B)")
    print("=" * 50)
    print(f"📊 하루 {POSTS_PER_DAY}회 포스팅 (완전 무료!)")
    print_bot_stats()

    setup_agents()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        print("\n🧪 테스트 모드")
        result = create_post()
        if result:
            post_id, ticker_yf, ticker_display, stance, author_id = result
            time.sleep(3)
            create_comment(post_id, ticker_display, stance, author_id)
        time.sleep(3)
        run_comment_round()
        print("\n✅ 테스트 완료!")
    else:
        schedule.every(15).minutes.do(run_every_30min)
        schedule.every().day.at("09:00").do(refresh_groq_trending)
        print(f"\n⏰ 스케줄러 시작: 15분마다 실행 / 매일 09:00 종목 갱신")
        print("Ctrl+C로 종료")
        print("\n트렌딩 종목 초기 갱신 중...")
        refresh_groq_trending()
        run_every_30min()
        while True:
            schedule.run_pending()
            time.sleep(60)