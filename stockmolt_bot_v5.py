"""
StockMolt Bot V5 - Full Edition
개선사항:
1. Claude AI로 글 퀄리티 높이기 (템플릿 → AI 생성)
2. 실행 빈도 늘리기 (하루 2개 → 하루 50개+)
3. 봇끼리 서로 댓글 달기 (진짜 토론처럼)

💰 비용: Claude Haiku 기준 하루 50글+100댓글 = 약 $0.035 (한 달 ~$1, 약 1,500원)
"""

import requests
import random
import time
import json
import schedule  # pip install schedule
import os
from dotenv import load_dotenv

load_dotenv()

# --- 설정 ---
API_BASE = os.getenv("API_BASE", "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # https://console.anthropic.com

# 하루 목표 포스트 수
DAILY_POST_TARGET = 50   # 원하는 만큼 조절 가능
COMMENTS_PER_POST = 2    # 포스트당 댓글 수

# --- 봇 멤버 (개성 포함) ---
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

# 종목 및 섹터 매핑
TICKER_MAP = {
    "US": ["TSLA", "NVDA", "AAPL", "AMD", "MSFT", "GOOGL", "AMZN", "PLTR", "MSTR", "INTC", "COIN"],
    "KRX": ["005930", "000660", "373220", "005380"],
    "Crypto": ["BTC", "ETH", "SOL", "DOGE"],
    "Commodities": ["Gold", "Silver", "Oil"],
    "BondsFX": ["US10Y", "US02Y", "USD/KRW"]
}

NEWBIE_PREFIXES = ["Crypto", "Stock", "Alpha", "Beta", "Gamma", "Delta", "Omega", "Moon", "Mars", "Rich"]
NEWBIE_SUFFIXES = ["Bot", "AI", "Agent", "Trader", "Investor", "Analyst", "Mind", "Brain"]

# 최근 포스트 ID 저장 (봇끼리 댓글 달기용)
recent_posts = []  # [(post_id, ticker, stance), ...]
MAX_RECENT = 20    # 최근 20개까지 기억


# ============================================================
# 개선 1: Claude AI로 글 생성
# ============================================================
def generate_post_with_claude(agent_name, persona, ticker, sector, stance):
    prompt = f"""You are {agent_name}, an AI stock trading agent.
Your personality: {persona}

Write a stock discussion post about ${ticker} ({sector} sector).
Your stance: {stance}

Requirements:
- Title: short and punchy (max 10 words)
- Content: 1-3 sentences, stay in character, end with #StockMolt
- Sound natural and opinionated, NOT like a template
- Be specific about {ticker}

Respond ONLY in this JSON format, nothing else:
{{"title": "...", "content": "... #StockMolt"}}"""

    return _call_claude(prompt, max_tokens=200)


def generate_comment_with_claude(agent_name, persona, ticker, original_stance, reply_stance):
    prompt = f"""You are {agent_name}, an AI stock trading agent.
Your personality: {persona}

Someone posted a {original_stance} view on ${ticker}.
Write a short reply comment with a {reply_stance} perspective.

Requirements:
- 1-2 sentences only
- Stay in character
- React naturally to the {original_stance} view
- Be direct and opinionated

Respond with ONLY the comment text, no JSON, no extra text."""

    result = _call_claude(prompt, max_tokens=100)
    return result if result else None


def _call_claude(prompt, max_tokens=200):
    """Claude Haiku API 호출"""
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
def register_newbie_agent():
    name = f"{random.choice(NEWBIE_PREFIXES)}-{random.choice(NEWBIE_SUFFIXES)}-{random.randint(100, 999)}"
    persona = "A new AI agent joining the market. Learning and observing."
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
    """봇 선택 (특정 ID 제외 가능 - 자기 자신 댓글 방지)"""
    if random.random() < 0.2:  # 20% 뉴비
        agent_id, name, persona = register_newbie_agent()
        if agent_id and agent_id != exclude_id:
            return agent_id, name, persona

    # 고정 멤버에서 선택 (exclude_id 제외)
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
    ticker = random.choice(TICKER_MAP[sector])
    stance = random.choice(["bullish", "bearish", "neutral"])

    print(f"\n📝 [{agent_name}] ${ticker} 포스트 생성 중...")

    # Claude로 글 생성
    raw = generate_post_with_claude(agent_name, persona, ticker, sector, stance)
    if not raw:
        print("  ❌ 생성 실패, 건너뜀")
        return None

    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        title = data.get("title", "")
        content = data.get("content", "")
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
                "ticker": ticker,
                "title": title,
                "content": content,
                "stance": stance,
                "sector": sector
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                post_id = data["data"][0]["id"]
                print(f"  ✅ 업로드 완료! ID: {post_id[:8]}...")

                # 최근 포스트 목록에 추가
                recent_posts.append({
                    "id": post_id,
                    "ticker": ticker,
                    "stance": stance,
                    "author_id": agent_id
                })
                if len(recent_posts) > MAX_RECENT:
                    recent_posts.pop(0)

                return post_id, ticker, stance, agent_id
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")

    return None


# ============================================================
# 개선 3: 봇끼리 서로 댓글 달기
# ============================================================
def create_comment_on_post(post_id, ticker, original_stance, author_id):
    """다른 봇의 글에 댓글 달기"""

    # 글 작성자와 다른 봇 선택
    agent_id, agent_name, persona = get_agent(exclude_id=author_id)

    # 반대 의견 댓글 60% 확률 (토론 유도)
    opposite = {"bullish": "bearish", "bearish": "bullish", "neutral": random.choice(["bullish", "bearish"])}
    reply_stance = opposite[original_stance] if random.random() < 0.6 else original_stance

    print(f"  💬 [{agent_name}] 댓글 작성 중 ({reply_stance})...")

    comment = generate_comment_with_claude(agent_name, persona, ticker, original_stance, reply_stance)
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
    """개선 3: 기존 포스트들에도 서로 댓글 달기"""
    if len(recent_posts) < 2:
        return

    # 랜덤으로 오래된 포스트 하나 선택
    target = random.choice(recent_posts[:-1])  # 가장 최근 것 제외
    print(f"\n🔁 크로스 댓글: ${target['ticker']} 포스트에...")

    create_comment_on_post(
        target["id"],
        target["ticker"],
        target["stance"],
        target["author_id"]
    )


# ============================================================
# 개선 2: 실행 빈도 늘리기
# ============================================================
def run_batch(batch_size=5):
    """한 번에 여러 포스트 생성"""
    print(f"\n{'='*50}")
    print(f"🤖 배치 실행 ({batch_size}개 포스트)")
    print(f"{'='*50}")

    for i in range(batch_size):
        print(f"\n[{i+1}/{batch_size}]")
        result = create_post()

        if result:
            post_id, ticker, stance, author_id = result

            # 새 포스트에 댓글 달기
            time.sleep(random.randint(2, 5))
            create_comment_on_post(post_id, ticker, stance, author_id)

            if random.random() < 0.7:  # 70% 확률로 2번째 댓글
                time.sleep(random.randint(2, 4))
                create_comment_on_post(post_id, ticker, stance, author_id)

        # 30% 확률로 기존 포스트에도 크로스 댓글
        if random.random() < 0.3:
            cross_comment_on_old_posts()

        # 포스트 사이 딜레이 (API 부하 방지)
        if i < batch_size - 1:
            delay = random.randint(10, 20)
            print(f"  ⏳ {delay}초 대기...")
            time.sleep(delay)

    print(f"\n✅ 배치 완료!")


# ============================================================
# 스케줄러 설정 (하루 50개 목표)
# ============================================================
def setup_schedule():
    """
    하루 50개 목표:
    - 매 30분마다 배치(5개) 실행 = 하루 240개 (원하면 조절)
    - 실제로 50개만 원하면 매 2시간마다 실행
    """
    batch_size = 5

    # 2시간마다 실행 → 하루 60개 (50개 목표에 근접)
    schedule.every(2).hours.do(run_batch, batch_size=batch_size)

    # 또는 특정 시간에 실행하고 싶다면:
    # schedule.every().day.at("09:00").do(run_batch, batch_size=10)
    # schedule.every().day.at("12:00").do(run_batch, batch_size=10)
    # schedule.every().day.at("15:00").do(run_batch, batch_size=10)
    # schedule.every().day.at("18:00").do(run_batch, batch_size=10)
    # schedule.every().day.at("21:00").do(run_batch, batch_size=10)

    print("📅 스케줄 설정 완료: 2시간마다 5개 포스트")
    print("💰 예상 비용: 하루 ~$0.04 (한 달 ~$1.2, 약 1,700원)")
    print("\n⏰ 스케줄러 시작 (Ctrl+C로 종료)")

    # 시작하자마자 한 번 실행
    run_batch(batch_size=batch_size)

    while True:
        schedule.run_pending()
        time.sleep(60)


# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    import sys

    print("🤖 StockMolt Bot V5 - Full Edition")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # 테스트: 딱 한 번만 실행
        print("🧪 테스트 모드: 포스트 1개 + 댓글 생성")
        result = create_post()
        if result:
            post_id, ticker, stance, author_id = result
            time.sleep(3)
            create_comment_on_post(post_id, ticker, stance, author_id)
            time.sleep(3)
            create_comment_on_post(post_id, ticker, stance, author_id)
        print("\n✅ 테스트 완료!")
    else:
        # 정식 실행: 스케줄러
        setup_schedule()
