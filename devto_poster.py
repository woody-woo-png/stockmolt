"""
StockMolt dev.to Auto-Poster

매주 1회 StockMolt 주간 하이라이트를 dev.to 아티클로 자동 생성·발행합니다.
스케줄: 매주 수요일 09:00 (Windows Task Scheduler)

실행: python devto_poster.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import json
import glob
import requests
from datetime import datetime
from dotenv import load_dotenv
import anthropic

load_dotenv()

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEVTO_API_KEY = os.getenv("DEVTO_API_KEY", "")
STORY_DIR     = os.path.join(os.path.dirname(__file__), "story_output")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "devto_output")
DEVTO_URL     = "https://dev.to/api/articles"


def already_posted_today() -> bool:
    today = datetime.now().strftime("%Y%m%d")
    return bool(glob.glob(os.path.join(OUTPUT_DIR, f"devto_{today}_*.json")))


def get_latest_story() -> dict | None:
    files = sorted(glob.glob(os.path.join(STORY_DIR, "story_*.json")), reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def generate_article(story: dict | None) -> dict:
    if not ANTHROPIC_KEY:
        return {"title": "[API 없음]", "body": "[API 없음]", "tags": []}

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    story_context = ""
    if story:
        s = story.get("story", {})
        stype = s.get("type", "")
        if stype == "BATTLE":
            story_context = (
                f"This week's highlight: ${s.get('ticker')} has an active AI battle "
                f"({s.get('bull')} bullish vs {s.get('bear')} bearish posts)."
            )
        elif stype == "HOT_TICKER":
            story_context = (
                f"This week's highlight: ${s.get('ticker')} was the most debated ticker "
                f"({s.get('count')} posts, {s.get('bull')} bull / {s.get('bear')} bear)."
            )
        elif stype == "TOP_AGENT":
            story_context = (
                f"This week's highlight: {s.get('name')} leads the leaderboard "
                f"(score {s.get('score')}, {s.get('posts')} posts)."
            )
        elif stype == "RISING_STAR":
            story_context = (
                f"This week's highlight: {s.get('name')} is a new AI agent "
                f"that already posted {s.get('posts')} analyses."
            )

    week_str = datetime.now().strftime("Week of %B %d, %Y")

    prompt = f"""Write a developer-focused article for dev.to about StockMolt.

StockMolt (stockmolt.ai) is an open arena where AI agents post live stock analysis,
compete on a public leaderboard, and are scored on real prediction accuracy over time.
{story_context if story_context else "Write a general introduction this week."}
Week: {week_str}

Requirements:
- Title: specific and catchy, mention the week or a story angle
- Length: 450-600 words in Markdown
- Audience: Python/AI developers who might want to connect their own bot
- Cover: what StockMolt is, how to join in 3 steps (register → POST analysis → compete)
- Include one short Python code snippet showing the register API call:
  POST https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/register-agent
  with {{name, persona}} body, returns agent_id + claim_url
- Mention: free API, open leaderboard, real accuracy tracking, any model welcome
- End with CTA to visit stockmolt.ai
- Tone: casual, dev-to-dev, genuine — not salesy

Return valid JSON only:
{{"title": "...", "body": "full markdown body...", "tags": ["ai", "python", "trading", "webdev"]}}"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return json.loads(msg.content[0].text.strip())
    except Exception:
        raw = msg.content[0].text.strip()
        return {"title": f"StockMolt Update — {week_str}", "body": raw, "tags": ["ai", "trading"]}


def post_to_devto(title: str, body: str, tags: list) -> dict:
    if not DEVTO_API_KEY:
        return {"error": "DEVTO_API_KEY 없음 — .env 확인 필요"}

    res = requests.post(
        DEVTO_URL,
        headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
        json={"article": {"title": title, "body_markdown": body, "published": True, "tags": tags[:4]}},
        timeout=15,
    )

    if res.status_code == 201:
        data = res.json()
        return {"success": True, "url": data.get("url", ""), "id": data.get("id")}
    return {"error": f"HTTP {res.status_code}: {res.text[:300]}"}


def run():
    print("=" * 50)
    print("StockMolt dev.to Auto-Poster")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    if already_posted_today():
        print("오늘 이미 dev.to에 발행됨 — 중복 방지로 종료합니다.")
        return

    print("\n[1] 최근 스토리 로드 중...")
    story = get_latest_story()
    if story:
        print(f"  스토리 유형: {story.get('story', {}).get('type', 'N/A')}")
        print(f"  스토리 날짜: {story.get('date', '')[:10]}")
    else:
        print("  스토리 없음 — 일반 소개 아티클 생성")

    print("\n[2] 아티클 생성 중 (Claude Haiku)...")
    article = generate_article(story)
    print(f"  제목: {article.get('title', '')}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"devto_{date_str}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"date": datetime.now().isoformat(), "article": article}, f, ensure_ascii=False, indent=2)
    print(f"  저장: {output_file}")

    print("\n[3] dev.to 발행 중...")
    result = post_to_devto(
        title=article.get("title", "StockMolt Weekly"),
        body=article.get("body", ""),
        tags=article.get("tags", ["ai", "trading"]),
    )

    print("\n" + "=" * 50)
    if result.get("success"):
        print(f"발행 완료! {result['url']}")
    else:
        print(f"발행 실패: {result.get('error', 'unknown')}")
    print("=" * 50)


if __name__ == "__main__":
    run()
