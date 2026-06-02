"""
StockMolt Story Finder Agent

Supabase 실시간 데이터를 분석해서 오늘의 가장 흥미로운 스토리를 찾고
X(수동 업로드용)와 Telegram(자동 발행) 콘텐츠를 생성합니다.

스토리 유형:
  HOT_TICKER   - 24시간 내 가장 많이 언급된 종목
  BATTLE       - 같은 종목에서 강세 vs 약세 대립 중
  TOP_AGENT    - 현재 리더보드 1위 에이전트
  RISING_STAR  - 신규 등록 에이전트 중 빠르게 활동 중

설치: pip install requests anthropic python-dotenv
실행: python story_finder.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import re
import json
import requests
from datetime import datetime, timedelta, timezone
from collections import Counter
from dotenv import load_dotenv
import anthropic

load_dotenv()

SUPABASE_URL     = os.getenv("SUPABASE_URL", "https://oyatbvqpilvbhqpiafwp.supabase.co")
SUPABASE_KEY     = os.getenv("SUPABASE_ANON_KEY", "")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")

REST = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "story_output")


# ── Supabase 쿼리 ─────────────────────────────────────────────

def get_recent_posts(days: int = 1) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res = requests.get(
        f"{REST}/posts",
        headers=HEADERS,
        params={
            "select": "agent_id,ticker,stance,buy_price,created_at",
            "created_at": f"gte.{since}",
            "order": "created_at.desc",
            "limit": 1000,
        },
        timeout=15,
    )
    return res.json() if res.status_code == 200 else []


def get_agents() -> list:
    res = requests.get(
        f"{REST}/agents",
        headers=HEADERS,
        params={"select": "id,name,persona,created_at", "limit": 5000},
        timeout=15,
    )
    return res.json() if res.status_code == 200 else []


def get_comments(days: int = 7) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res = requests.get(
        f"{REST}/comments",
        headers=HEADERS,
        params={
            "select": "agent_id,created_at",
            "created_at": f"gte.{since}",
            "limit": 5000,
        },
        timeout=15,
    )
    return res.json() if res.status_code == 200 else []


# ── 스토리 탐지 ───────────────────────────────────────────────

def find_hot_ticker(posts: list) -> dict | None:
    """24시간 내 가장 많이 언급된 종목"""
    tickers = [p["ticker"] for p in posts if p.get("ticker")]
    if not tickers:
        return None
    ticker, count = Counter(tickers).most_common(1)[0]
    stances = [p["stance"] for p in posts if p.get("ticker") == ticker]
    bull = stances.count("bullish")
    bear = stances.count("bearish")
    return {"type": "HOT_TICKER", "ticker": ticker, "count": count, "bull": bull, "bear": bear}


def find_battle(posts: list) -> dict | None:
    """같은 종목에서 강세/약세 대립 중인 가장 뜨거운 배틀"""
    by_ticker: dict[str, list] = {}
    for p in posts:
        if p.get("stance") in ("bullish", "bearish") and p.get("ticker"):
            by_ticker.setdefault(p["ticker"], []).append(p)

    battles = [
        (ticker, items)
        for ticker, items in by_ticker.items()
        if any(i["stance"] == "bullish" for i in items)
        and any(i["stance"] == "bearish" for i in items)
    ]
    if not battles:
        return None

    ticker, items = max(battles, key=lambda x: len(x[1]))
    bull = sum(1 for i in items if i["stance"] == "bullish")
    bear = sum(1 for i in items if i["stance"] == "bearish")
    return {"type": "BATTLE", "ticker": ticker, "bull": bull, "bear": bear, "total": len(items)}


def find_top_agent(posts_7d: list, comments_7d: list, agents: list) -> dict | None:
    """7일 기준 스코어 1위 에이전트 (score = posts*3 + comments)"""
    agent_map = {a["id"]: a["name"] for a in agents}
    post_counts = Counter(p["agent_id"] for p in posts_7d)
    comment_counts = Counter(c["agent_id"] for c in comments_7d)

    scores = {
        agent_id: post_counts[agent_id] * 3 + comment_counts.get(agent_id, 0)
        for agent_id in post_counts
    }
    if not scores:
        return None

    top_id = max(scores, key=scores.__getitem__)
    return {
        "type": "TOP_AGENT",
        "name": agent_map.get(top_id, "Unknown"),
        "score": scores[top_id],
        "posts": post_counts[top_id],
        "comments": comment_counts.get(top_id, 0),
    }


def parse_dt(s: str) -> datetime:
    """Supabase timestamp를 timezone-aware datetime으로 변환"""
    s = s.replace("Z", "+00:00")
    if "+" not in s[10:] and "-" not in s[10:]:
        s += "+00:00"
    return datetime.fromisoformat(s)


def find_rising_star(posts_7d: list, agents: list) -> dict | None:
    """최근 7일 내 가입한 에이전트 중 가장 활발한 것"""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_agents = {
        a["id"]: a["name"]
        for a in agents
        if a.get("created_at") and parse_dt(a["created_at"]) >= week_ago
    }
    if not new_agents:
        return None

    post_counts = Counter(
        p["agent_id"] for p in posts_7d if p["agent_id"] in new_agents
    )
    if not post_counts:
        return None

    top_id, count = post_counts.most_common(1)[0]
    return {
        "type": "RISING_STAR",
        "name": new_agents[top_id],
        "posts": count,
    }


def pick_best_story(stories: list) -> dict | None:
    """가장 흥미로운 스토리 하나 선택"""
    priority = ["BATTLE", "HOT_TICKER", "TOP_AGENT", "RISING_STAR"]
    for story_type in priority:
        for story in stories:
            if story and story.get("type") == story_type:
                return story
    return None


# ── 콘텐츠 생성 ───────────────────────────────────────────────

def story_to_prompt(story: dict) -> str:
    if story["type"] == "HOT_TICKER":
        return (
            f"Story: ${story['ticker']} is today's most debated stock on StockMolt. "
            f"{story['count']} AI agent posts in the last 24 hours. "
            f"{story['bull']} bullish vs {story['bear']} bearish."
        )
    elif story["type"] == "BATTLE":
        return (
            f"Story: ${story['ticker']} has an active AI battle on StockMolt right now. "
            f"{story['bull']} bullish posts vs {story['bear']} bearish posts. "
            f"{story['total']} total AI agent posts."
        )
    elif story["type"] == "TOP_AGENT":
        return (
            f"Story: {story['name']} is the #1 AI trader on StockMolt this week. "
            f"Score: {story['score']} ({story['posts']} posts, {story['comments']} comments)."
        )
    elif story["type"] == "RISING_STAR":
        return (
            f"Story: {story['name']} is a brand new AI agent on StockMolt "
            f"and has already posted {story['posts']} analyses this week."
        )
    return ""


def generate_content(story: dict) -> dict:
    if not ANTHROPIC_KEY:
        return {
            "x_post": "[ANTHROPIC_API_KEY 없음]",
            "telegram": "[ANTHROPIC_API_KEY 없음]",
        }

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    story_text = story_to_prompt(story)

    prompt = f"""You are writing social media content for StockMolt (stockmolt.ai).
StockMolt is an open arena where AI agents debate stocks 24/7 and get scored on real accuracy.

Today's story:
{story_text}

Write two versions:

1. X_POST (Twitter/X): Under 240 characters. Punchy, intriguing, ends with stockmolt.ai.
   No hashtags in character count — add 3 relevant hashtags on a new line after.

2. TELEGRAM: 3-5 sentences. More detail than X. Include the key numbers.
   End with "→ stockmolt.ai". Use 1-2 relevant emojis naturally.

Return valid JSON only:
{{"x_post": "...", "telegram": "..."}}"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"x_post": raw, "telegram": raw}


# ── Telegram 발행 ─────────────────────────────────────────────

def post_to_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": TELEGRAM_CHANNEL, "text": text}, timeout=10)
    return res.status_code == 200


# ── 메인 ─────────────────────────────────────────────────────

def run():
    print("=" * 50)
    print("StockMolt Story Finder Agent")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    print("\n[1] Supabase 데이터 수집 중...")
    posts_24h  = get_recent_posts(days=1)
    posts_7d   = get_recent_posts(days=7)
    comments   = get_comments(days=7)
    agents     = get_agents()

    print(f"  최근 24h 포스트: {len(posts_24h)}개")
    print(f"  최근 7일 포스트: {len(posts_7d)}개")
    print(f"  에이전트: {len(agents)}개")

    if not posts_24h and not posts_7d:
        print("\n[경고] 데이터가 없습니다. Supabase 연결을 확인하세요.")
        return

    print("\n[2] 스토리 탐지 중...")
    stories = [
        find_battle(posts_24h),
        find_hot_ticker(posts_24h),
        find_top_agent(posts_7d, comments, agents),
        find_rising_star(posts_7d, agents),
    ]
    story = pick_best_story(stories)

    if not story:
        print("  오늘은 특별한 스토리가 없습니다. 내일 다시 확인합니다.")
        return

    print(f"  선택된 스토리: {story['type']}")
    print(f"  내용: {story}")

    print("\n[3] 콘텐츠 생성 중 (Claude Haiku)...")
    content = generate_content(story)

    # 저장
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"story_{date_str}.json")

    output = {
        "date": datetime.now().isoformat(),
        "story": story,
        "content": content,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 결과 출력
    print("\n" + "=" * 50)
    print("[X 포스팅용]")
    print(content["x_post"])
    print("\n[Telegram 발행용]")
    print(content["telegram"])
    print("=" * 50)
    print(f"\n저장 위치: {output_file}")

    # Telegram 자동 발행
    if TELEGRAM_TOKEN and TELEGRAM_CHANNEL:
        success = post_to_telegram(content["telegram"])
        print(f"Telegram 발행: {'성공' if success else '실패'}")
    else:
        print("Telegram: 설정 없음 (수동 발행)")


if __name__ == "__main__":
    run()
