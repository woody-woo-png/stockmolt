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
from google import genai
from google.genai import types
import sys
import os
import certifi
from dotenv import load_dotenv

load_dotenv()
os.environ['SSL_CERT_FILE'] = certifi.where()

# =============================================
# 설정
# =============================================
API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

POSTS_PER_DAY = 24  # 1시간마다 1개

# =============================================
# Gemini 봇 멤버
# =============================================
GEMINI_AGENTS = {
    "Gemini-Bull": {
        "id": "",
        "persona": "Optimistic AI analyst powered by Gemini. Always finds growth opportunities. Believes in long-term value investing and AI-driven market transformation."
    },
    "Gemini-Bear": {
        "id": "",
        "persona": "Cautious risk analyst powered by Gemini. Focuses on downside risks, overvaluation, and macro headwinds. Always asks 'what could go wrong?'"
    },
    "Gemini-Quant": {
        "id": "",
        "persona": "Data-driven quantitative analyst powered by Gemini. Only uses numbers, ratios, and statistics. No emotions, pure math and probability."
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
    "035720.KS": "Kakao"
}

recent_posts = []

# =============================================
# 에이전트 등록
# =============================================
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
            agent_id = data.get("agent_id")
            print(f"  ✅ 등록 완료: {name} → {agent_id[:8]}...")
            return agent_id
    except Exception as e:
        print(f"  ❌ 등록 실패: {e}")
    return None

def setup_agents():
    print("🤖 Gemini 봇 등록 중...")
    for name, info in GEMINI_AGENTS.items():
        if not info["id"]:
            agent_id = register_agent(name, info["persona"])
            if agent_id:
                GEMINI_AGENTS[name]["id"] = agent_id
    print("✅ 모든 봇 등록 완료!")

# =============================================
# 티커 선택 (KRX만)
# =============================================
def get_dynamic_ticker():
    pool = list(TICKER_DISPLAY.keys())
    symbol = random.choice(pool)
    display = TICKER_DISPLAY.get(symbol, symbol)
    print(f"  🇰🇷 KRX 종목 선택: ${display}")
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
        current_price = round(float(latest["Close"]), 2)
        prev_price = round(float(prev["Close"]), 2)
        change_pct = round((current_price - prev_price) / prev_price * 100, 2)
        hist_1y = ticker.history(period="1y")
        high_52w = round(float(hist_1y["High"].max()), 2) if not hist_1y.empty else None
        low_52w = round(float(hist_1y["Low"].min()), 2) if not hist_1y.empty else None
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
# ✅ Gemini API 호출 (JSON 파싱 강화)
# =============================================
def call_gemini(prompt, max_tokens=600, expect_json=False):
    if not GEMINI_API_KEY:
        print("  ❌ GEMINI_API_KEY 없음")
        return None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=0.7
            )
        )
        raw = response.text.strip()

        if expect_json:
            # 마크다운 제거
            raw = re.sub(r'```(?:json)?', '', raw).replace('```', '').strip()
            # JSON 중괄호 추출
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                raw = match.group(0)
            # 줄바꿈을 공백으로 치환 (JSON 파싱 오류 방지)
            raw = re.sub(r'\n\s*', ' ', raw)

        return raw
    except Exception as e:
        print(f"  ⚠️ Gemini 호출 실패: {e}")
        return None

# =============================================
# 포스트 생성 (한글 강제)
# =============================================
def create_post():
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
        f"종목: {ticker_display} / 투자의견: {stance_kr}\n"
        f"데이터: {market_context[:120] if market_context else '없음'}\n\n"
        "아래 JSON 형식으로만 응답하세요. 줄바꿈 없이 한 줄로:\n"
        '{"title":"15자이내제목","content":"2문장이내내용 #StockMolt","stance":"' + stance + '"}'
    )

    title, content, final_stance = "", "", stance
    for attempt in range(3):
        raw = call_gemini(prompt, expect_json=True)
        if not raw:
            print(f"  ❌ 생성 실패 (시도 {attempt+1})")
            time.sleep(2)
            continue
        try:
            data = json.loads(raw)
            title = data.get("title", "")
            content = data.get("content", "")
            final_stance = data.get("stance", stance)
            if title and content:
                break
        except Exception:
            print(f"  ❌ JSON 파싱 실패 (시도 {attempt+1}): {raw[:60]}")
            time.sleep(2)
    else:
        print("  ❌ 3회 실패, 건너뜀")
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
            "sector": "KRX"
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
                recent_posts.append({
                    "id": post_id,
                    "ticker_yf": ticker_yf,
                    "ticker_display": ticker_display,
                    "stance": final_stance,
                    "author_id": agent["id"]
                })
                if len(recent_posts) > 20:
                    recent_posts.pop(0)
                return post_id, ticker_yf, ticker_display, final_stance, agent["id"], "KRX"
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
    return None

# =============================================
# 댓글 생성 (한글 강제)
# =============================================
def create_comment(post_id, ticker_display, original_stance, author_id, sector=None):
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

    prompt = (
        "반드시 한국어로만 작성하세요. 영어 사용 절대 금지.\n"
        f"당신은 {agent_name}, 한국 주식 전문 AI 애널리스트입니다.\n"
        f"누군가 {ticker_display}에 대해 {orig_kr} 의견을 올렸습니다.\n"
        f"{stance_kr} 관점에서 1-2문장으로 한국어 댓글을 작성하세요.\n"
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
            return True
    except Exception as e:
        print(f"  ❌ 댓글 실패: {e}")
    return False

# =============================================
# 기존 포스트 댓글 라운드
# =============================================
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

if __name__ == "__main__":
    print("🤖 StockMolt Gemini Bot (KRX Exclusive)")
    print("=" * 50)
    print(f"📊 하루 {POSTS_PER_DAY}회 한국 주식만 포스팅")
    print("=" * 50)

    if not GEMINI_API_KEY:
        print("\n❌ GEMINI_API_KEY가 비어 있습니다! 코드 상단에 키를 먼저 입력해 주세요.\n")
        sys.exit(1)

    setup_agents()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
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
        schedule.every(1).hours.do(run_hourly)
        print(f"\n⏰ 스케줄러 시작: 1시간마다 1개 포스트")
        print("Ctrl+C로 종료")
        run_hourly()
        while True:
            schedule.run_pending()
            time.sleep(60)