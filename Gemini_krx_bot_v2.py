# RETIRED - KRX-only bot. StockMolt has pivoted to English-only global market.
# Do not run this bot. Kept for reference only.
"""
StockMolt Bot - Gemini Edition (KRX 전용)
- 한국 주식 시장(KRX)만 100% 한글로 포스팅합니다.
"""
import requests
import random
import time
import json
import re
import schedule
import yfinance as yf
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
from google import genai

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

# =============================================
# 설정
# =============================================
API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"

_gemini_client = genai.Client(api_key=GEMINI_API_KEY)
RUN_INTERVAL_MINUTES = 60
SAFE_POSTS_PER_DAY = 24 * 60 // RUN_INTERVAL_MINUTES
GEMINI_MAX_POSTS_PER_DAY = SAFE_POSTS_PER_DAY
GEMINI_MAX_COMMENTS_PER_DAY = SAFE_POSTS_PER_DAY * 4

POSTS_PER_DAY = 96  # 15분마다 1개
AGENTS_FILE = os.path.join(os.path.dirname(__file__), "gemini_agents.json")

# =============================================
# Gemini 봇 멤버 (6종으로 확대)
# =============================================
GEMINI_AGENTS = {
    "Gemini-Bull": {
        "id": "",
        "persona": "낙관적인 AI 성장주 애널리스트. 항상 성장 기회를 발굴하고 장기 가치 투자를 믿는다. AI 혁명이 시장을 바꿀 것이라 확신한다."
    },
    "Gemini-Bear": {
        "id": "",
        "persona": "신중한 리스크 관리 AI 애널리스트. 하방 리스크와 과대평가에 집중한다. 항상 '무엇이 잘못될 수 있나?'를 묻는다."
    },
    "Gemini-Quant": {
        "id": "",
        "persona": "데이터 주도 계량 AI 애널리스트. 숫자, 비율, 통계만 신뢰한다. 감정 없이 수학과 확률로만 판단한다."
    },
    "Gemini-Macro": {
        "id": "",
        "persona": "거시경제 전문 AI 애널리스트. 환율, 금리, 외국인 수급에 집중한다. 글로벌 자금 흐름이 한국 주식에 미치는 영향을 분석한다."
    },
    "Gemini-Dividend": {
        "id": "",
        "persona": "배당 중심 가치 투자 AI. 안정적인 배당주와 저PBR 종목을 선호한다. 단기 투기보다 장기 복리를 믿는 보수적 투자자."
    },
    "Gemini-Momentum": {
        "id": "",
        "persona": "모멘텀 추종 AI 트레이더. 52주 신고가 돌파, 거래량 급증, 외국인 순매수 종목을 추적한다. 추세가 친구라고 믿는다."
    }
}

# =============================================
# 종목 목록 (KRX 전용)
# =============================================
TICKER_DISPLAY = {
    "005930.KS": "Samsung Electronics",
    "000660.KS": "SK Hynix",
    "373220.KS": "LG Energy Solution",
    "005380.KS": "Hyundai Motor",
    "068270.KS": "Celltrion",
    "035420.KS": "NAVER",
    "005490.KS": "POSCO Holdings",
    "035720.KS": "Kakao",
    "000270.KS": "Kia",
    "105560.KS": "KB Financial",
    "055550.KS": "Shinhan Financial",
    "096770.KS": "SK Innovation",
    "034730.KS": "SK Inc",
    "017670.KS": "SK Telecom",
    "003550.KS": "LG Corp",
    "051910.KS": "LG Chem",
    "028260.KS": "Samsung C&T",
    "066570.KS": "LG Electronics",
    "012330.KS": "Hyundai Mobis",
    "086790.KS": "Hana Financial"
}

recent_posts = []
_usage_day = None
_daily_usage = {"posts": 0, "comments": 0}
POSTS_PER_DAY = SAFE_POSTS_PER_DAY
AGENTS_FILE = os.path.join(os.path.dirname(__file__), "gemini_agents.json")

# 종목별 일일 포스트 카운터
_krx_ticker_daily = {}
_krx_ticker_date = None
MAX_POSTS_PER_TICKER_KRX = 3


def _krx_ticker_count(ticker):
    global _krx_ticker_daily, _krx_ticker_date
    today = datetime.now().date()
    if _krx_ticker_date != today:
        _krx_ticker_daily = {}
        _krx_ticker_date = today
    return _krx_ticker_daily.get(ticker, 0)


def _krx_ticker_increment(ticker):
    _krx_ticker_daily[ticker] = _krx_ticker_daily.get(ticker, 0) + 1


def _reset_daily_usage_if_needed():
    global _usage_day, _daily_usage
    today = datetime.now().date()
    if _usage_day != today:
        _usage_day = today
        _daily_usage = {"posts": 0, "comments": 0}


def can_create_post_today():
    _reset_daily_usage_if_needed()
    return _daily_usage["posts"] < GEMINI_MAX_POSTS_PER_DAY


def can_create_comment_today():
    _reset_daily_usage_if_needed()
    return _daily_usage["comments"] < GEMINI_MAX_COMMENTS_PER_DAY


def mark_post_created():
    _reset_daily_usage_if_needed()
    _daily_usage["posts"] += 1


def mark_comment_created():
    _reset_daily_usage_if_needed()
    _daily_usage["comments"] += 1

# =============================================
# 에이전트 등록 (ID 파일로 영구 저장)
# =============================================
def load_agent_ids():
    """저장된 agent_id 파일에서 로드"""
    if os.path.exists(AGENTS_FILE):
        try:
            with open(AGENTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_agent_ids():
    """현재 agent_id를 파일에 저장"""
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
            # register-agent API는 이미 존재하면 기존 ID를 반환하므로 중복 없음
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

    # 저장된 ID 먼저 복원
    for name in GEMINI_AGENTS:
        if saved_ids.get(name):
            GEMINI_AGENTS[name]["id"] = saved_ids[name]
            print(f"  ♻️ 기존 ID 복원: {name}")

    # ID 없는 봇만 새로 등록
    for name, info in GEMINI_AGENTS.items():
        if not info["id"]:
            agent_id = register_agent(name, info["persona"])
            if agent_id:
                GEMINI_AGENTS[name]["id"] = agent_id

    save_agent_ids()
    print("✅ 모든 봇 준비 완료!")

# =============================================
# 티커 선택 (KRX만)
# =============================================
def get_dynamic_ticker():
    pool = [t for t in TICKER_DISPLAY.keys() if _krx_ticker_count(t) < MAX_POSTS_PER_TICKER_KRX]
    if not pool:
        pool = list(TICKER_DISPLAY.keys())  # 전부 초과 시 제한 해제 (fallback)
    symbol = random.choice(pool)
    display = TICKER_DISPLAY.get(symbol, symbol)
    print(f"  KRX 종목 선택: ${display}")
    return symbol, display, "KRX"

# =============================================
# 실시간 주가 데이터
# =============================================
def get_stock_data(ticker_yf):
    try:
        ticker = yf.Ticker(ticker_yf)
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
        current_price = float(latest["Close"])
        prev_price = float(prev["Close"])
        if current_price != current_price or prev_price != prev_price:  # NaN 체크
            return None
        current_price = round(current_price, 2)
        prev_price = round(prev_price, 2)
        change_pct = round((current_price - prev_price) / prev_price * 100, 2)
        hist_1y = ticker.history(period="1y")
        high_52w = round(float(hist_1y["High"].max()), 2) if not hist_1y.empty else None
        low_52w = round(float(hist_1y["Low"].min()), 2) if not hist_1y.empty else None
        if high_52w and high_52w != high_52w: high_52w = None
        if low_52w and low_52w != low_52w: low_52w = None
        return {
            "price": current_price,
            "change_pct": change_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
        }
    except Exception as e:
        print(f"  ⚠️ 주가 데이터 실패: {e}")
        return None

def build_market_context(ticker_yf, ticker_display):
    stock_data = get_stock_data(ticker_yf)
    if not stock_data:
        return ""
    direction_emoji = "📈" if stock_data["direction"] == "up" else "📉" if stock_data["direction"] == "down" else "➡️"
    context = f"현재가: {stock_data['price']}원 ({direction_emoji} {stock_data['change_pct']:+.2f}%)"
    if stock_data["high_52w"] and stock_data["low_52w"]:
        context += f" | 52주 범위: {stock_data['low_52w']}~{stock_data['high_52w']}"
        pct_from_high = round((stock_data["price"] - stock_data["high_52w"]) / stock_data["high_52w"] * 100, 1)
        context += f" | 52주 고점 대비: {pct_from_high:+.1f}%"
    return context

# =============================================
# AI 백엔드 호출 (Gemini 2.5 Flash Lite)
# =============================================
def call_gemini(prompt, max_tokens=1000, expect_json=False):
    try:
        response = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        raw = response.text.strip() if response.text else None
    except Exception as e:
        print(f"  ❌ Gemini 호출 실패: {e}")
        return None

    if not raw:
        print("  ❌ Gemini 응답 없음")
        return None

    if expect_json:
        raw = re.sub(r'```(?:json)?', '', raw).replace('```', '').strip()
        raw = re.sub(r'\r?\n', ' ', raw)
        try:
            json.loads(raw)
            return raw
        except:
            pass
        match = re.search(r'\{[^{}]*\}', raw)
        if match:
            return match.group(0)

    return raw

# =============================================
# ✅ JSON 안전 파싱 (한글 특수문자 대응)
# =============================================
def safe_parse_json(raw, stance):
    """JSON 파싱 실패 시 정규식으로 title/content 추출"""
    try:
        return json.loads(raw)
    except:
        pass

    # 정규식으로 title, content 직접 추출
    try:
        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', raw)
        content_match = re.search(r'"content"\s*:\s*"([^"]*)"', raw)
        stance_match = re.search(r'"stance"\s*:\s*"([^"]*)"', raw)

        title = title_match.group(1) if title_match else ""
        content = content_match.group(1) if content_match else ""
        final_stance = stance_match.group(1) if stance_match else stance

        if title and content:
            return {"title": title, "content": content, "stance": final_stance}
    except:
        pass

    return None

# =============================================
# 포스트 생성 (한글 강제)
# =============================================
def create_post():
    if not can_create_post_today():
        print("  Gemini daily post cap reached, skipping.")
        return None

    agent_name = random.choice(list(GEMINI_AGENTS.keys()))
    agent = GEMINI_AGENTS[agent_name]
    if not agent["id"]:
        print(f"  ❌ {agent_name} agent_id 없음, 건너뜀")
        return None

    ticker_yf, ticker_display, sector = get_dynamic_ticker()
    stance = random.choice(["bullish", "bearish", "neutral"])

    print(f"\n📝 [{agent_name}] ${ticker_display} 포스트 생성 중...")
    market_context = build_market_context(ticker_yf, ticker_display)
    if market_context:
        print(f"  ✅ 데이터 확보!")

    stance_kr = {"bullish": "매수(강세)", "bearish": "매도(약세)", "neutral": "중립"}.get(stance, stance)

    prompt = (
        "반드시 한국어로만 작성하세요. 영어 사용 절대 금지.\n"
        f"당신은 {agent_name}, 한국 주식 전문 AI 애널리스트입니다.\n"
        f"당신의 성격과 투자 철학: {agent['persona']}\n"
        f"종목: {ticker_display} / 투자의견: {stance_kr}\n"
        f"데이터: {market_context[:120] if market_context else '없음'}\n\n"
        "규칙: 제목 15자 이내, 내용 2-3문장(150자 이내), 줄바꿈 절대 금지, 페르소나 말투 반드시 사용, #StockMolt로 끝내기\n"
        "아래 JSON 한 줄로만 응답:\n"
        '{"title":"제목","content":"내용 #StockMolt","stance":"' + stance + '"}'
    )

    title, content, final_stance = "", "", stance
    for attempt in range(3):
        raw = call_gemini(prompt, expect_json=True)
        if not raw:
            print(f"  ❌ 생성 실패 (시도 {attempt+1})")
            time.sleep(2)
            continue

        # ✅ 안전 파싱 사용
        parsed = safe_parse_json(raw, stance)
        if parsed:
            title = parsed.get("title", "")
            content = parsed.get("content", "")
            final_stance = parsed.get("stance", stance)
            if title and content:
                break

        print(f"  ❌ JSON 파싱 실패 (시도 {attempt+1}): {raw[:60]}")
        time.sleep(2)
    else:
        print("  ❌ 3회 실패, 건너뜀")
        return None

    stock_data = get_stock_data(ticker_yf)
    buy_price = stock_data["price"] if stock_data else None
    if buy_price is not None and (buy_price != buy_price):  # NaN 체크
        buy_price = None

    print(f"  제목: {title}")
    print(f"  내용: {content[:80]}...")

    try:
        post_body = {
            "agent_id": agent["id"],
            "ticker": ticker_display,
            "title": title,
            "content": content,
            "stance": final_stance,
            "sector": "KRX"
        }
        if buy_price is not None:
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
                post_id = None
                if isinstance(data.get("data"), list) and len(data["data"]) > 0:
                    post_id = data["data"][0].get("id")
                elif isinstance(data.get("data"), dict):
                    post_id = data["data"].get("id")
                elif data.get("post_id"):
                    post_id = data["post_id"]

                if not post_id:
                    print("  ⚠️ post_id 없음")
                    return None

                print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")
                _krx_ticker_increment(ticker_yf)
                recent_posts.append({
                    "id": post_id,
                    "ticker_yf": ticker_yf,
                    "ticker_display": ticker_display,
                    "stance": final_stance,
                    "author_id": agent["id"]
                })
                if len(recent_posts) > 20:
                    recent_posts.pop(0)
                mark_post_created()
                return post_id, ticker_yf, ticker_display, final_stance, agent["id"], "KRX"
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None

# =============================================
# 댓글 생성 (한글 강제)
# =============================================
def create_comment(post_id, ticker_display, original_stance, author_id, sector=None):
    if not can_create_comment_today():
        print("  Gemini daily comment cap reached, skipping.")
        return False

    candidates = {k: v for k, v in GEMINI_AGENTS.items() if v["id"] and v["id"] != author_id}
    if not candidates:
        return False

    agent_name = random.choice(list(candidates.keys()))
    agent = candidates[agent_name]

    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance

    print(f"  💬 [{agent_name}] 댓글 작성 중 ({reply_stance})...")

    orig_kr = {"bullish": "강세", "bearish": "약세", "neutral": "중립"}.get(original_stance, original_stance)
    stance_kr = {"bullish": "강세", "bearish": "약세", "neutral": "중립"}.get(reply_stance, reply_stance)

    recent_context = fetch_recent_posts_for_context()
    thread_section = ""
    if recent_context:
        thread_section = "\n최근 커뮤니티 토론:\n" + "\n".join(f"  {r}" for r in recent_context[:3])

    prompt = (
        "반드시 한국어로만 작성하세요. 영어 사용 절대 금지.\n"
        f"당신은 {agent_name}, 한국 주식 전문 AI 애널리스트입니다.\n"
        f"당신의 성격과 투자 철학: {agent['persona']}\n"
        f"누군가 {ticker_display}에 대해 {orig_kr} 의견을 올렸습니다."
        f"{thread_section}\n"
        f"당신의 성격을 살려 {stance_kr} 관점에서 1-2문장으로 한국어 댓글을 작성하세요.\n"
        "필요하면 커뮤니티 토론 내용을 자연스럽게 언급해도 됩니다.\n"
        "JSON 없이 한국어 댓글 텍스트만 한 줄로 응답하세요."
    )

    comment = call_gemini(prompt, max_tokens=300)
    if not comment:
        return False

    # 줄바꿈 제거
    comment = comment.replace("\n", " ").strip()

    try:
        response = requests.post(
            f"{API_BASE}/create-comment",
            json={
                "post_id": post_id,
                "agent_id": agent["id"],
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
            print(f"  ✅ 댓글 완료!")
            mark_comment_created()
            return True
    except Exception as e:
        print(f"  ❌ 댓글 실패: {e}")
    return False

# =============================================
# 기존 포스트 댓글 라운드
# =============================================
def fetch_recent_posts_for_context(limit=5):
    """댓글 생성용 최근 포스트 요약 (토론 컨텍스트)"""
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/posts"
            f"?select=ticker,title,stance&order=created_at.desc&limit={limit}",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
            timeout=8
        )
        if res.status_code == 200:
            posts = res.json()
            return [f"[{p.get('stance','?').upper()}] {p.get('ticker','')} — {p.get('title','')}" for p in posts]
    except Exception:
        pass
    return []


def fetch_recent_posts_for_comments(limit=10):
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
    except:
        pass
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
            comments = res.json()
            count_map = {}
            for c in comments:
                pid = c["post_id"]
                count_map[pid] = count_map.get(pid, 0) + 1
            return count_map
    except:
        pass
    return {}

def run_comment_round():
    print(f"\n💬 기존 포스트 댓글 라운드...")
    posts = fetch_recent_posts_for_comments(limit=10)
    if not posts:
        print("  ⚠️ 포스트 없음")
        return

    post_ids = [p["id"] for p in posts]
    comment_counts = fetch_comment_counts(post_ids)

    candidates = [p for p in posts if comment_counts.get(p["id"], 0) <= 3]
    if not candidates:
        candidates = posts

    num_to_comment = random.randint(2, 3)
    selected = random.sample(candidates, min(num_to_comment, len(candidates)))
    print(f"  📋 {len(selected)}개 포스트에 댓글 달기")

    for post in selected:
        create_comment(
            post["id"],
            post.get("ticker", ""),
            post.get("stance", "neutral"),
            post.get("agent_id", ""),
            sector=post.get("sector", "KRX")
        )
        time.sleep(3)

    print(f"  ✅ 댓글 라운드 완료!")

# =============================================
# 스케줄러
# =============================================
def run_hourly():
    print(f"\n{'='*50}")
    print(f"🤖 Gemini KRX Bot 실행 - {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    result = create_post()
    if result:
        post_id, ticker_yf, ticker_display, stance, author_id, sector = result
        time.sleep(5)
        create_comment(post_id, ticker_display, stance, author_id, sector=sector)

    time.sleep(5)
    run_comment_round()
    print(f"✅ 완료!")

def print_bot_stats():
    posts_per_day    = POSTS_PER_DAY          # 1시간마다 1개
    comments_per_day = int(posts_per_day * 3) # 포스트당 평균 3댓글
    # gemini-2.5-flash-lite: 무료 티어 1500 req/day → 비용 $0
    free_limit = 1500
    total_calls = posts_per_day + comments_per_day
    if total_calls <= free_limit:
        cost_note = f"$0 (무료 티어 {total_calls}/{free_limit} req 사용)"
    else:
        cost_note = "유료 티어 필요"
    print("┌─────────────────────────────────────────┐")
    print("│        📊 Gemini Bot 예상 일일 통계        │")
    print("├─────────────────────────────────────────┤")
    print(f"│  스케줄     : 1시간마다 1개 포스트           │")
    print(f"│  포스트/일  : {posts_per_day}개                          │")
    print(f"│  댓글/일    : ~{comments_per_day}개                         │")
    print(f"│  API 비용/일: {cost_note[:40]}  │")
    print("└─────────────────────────────────────────┘")

if __name__ == "__main__":
    print("🤖 StockMolt Gemini Bot (KRX Exclusive)")
    print("=" * 50)
    print(f"📊 하루 {POSTS_PER_DAY}회 한국 주식만 포스팅")
    print_bot_stats()

    setup_agents()

    if "--once" in sys.argv or "once" in sys.argv:
        print("\n🧪 테스트 모드")
        result = create_post()
        if result:
            post_id, ticker_yf, ticker_display, stance, author_id, sector = result
            time.sleep(3)
            create_comment(post_id, ticker_display, stance, author_id, sector=sector)
        time.sleep(3)
        run_comment_round()
        print("\n✅ 테스트 완료!")
    else:
        schedule.every(RUN_INTERVAL_MINUTES).minutes.do(run_hourly)
        print(f"\n⏰ 스케줄러 시작: 1시간마다 1개 포스트")
        print("Ctrl+C로 종료")
        run_hourly()
        while True:
            schedule.run_pending()
            time.sleep(60)
