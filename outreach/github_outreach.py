"""
StockMolt GitHub Developer Outreach Agent

GitHub에서 AI 트레이딩 봇 개발자를 찾아
개인화된 초대 메시지를 자동 생성합니다.
발송은 직접 해야 합니다 (GitHub DM / 이메일).

설치: pip install requests anthropic python-dotenv
실행: python github_outreach.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import csv
import time
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import anthropic

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GMAIL_USER      = os.getenv("GMAIL_USER", "")
GMAIL_APP_PW    = os.getenv("GMAIL_APP_PASSWORD", "")
OUTPUT_DIR      = os.path.join(os.path.dirname(__file__), "results")
SENT_LOG        = os.path.join(OUTPUT_DIR, "sent_emails.txt")

GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# 검색 쿼리 목록 — 다양한 키워드로 개발자 탐색
SEARCH_QUERIES = [
    "AI stock trading bot python",
    "LLM stock prediction agent",
    "algorithmic trading openai",
    "stock analysis AI agent python",
    "trading bot claude anthropic",
]

MIN_STARS       = 3      # 너무 초기 프로젝트 제외
MAX_AGE_DAYS    = 365    # 1년 이상 업데이트 없는 레포 제외
MAX_PER_QUERY   = 8      # 쿼리당 최대 레포 수


def search_repos(query: str) -> list:
    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "updated",
        "order": "desc",
        "per_page": MAX_PER_QUERY,
    }
    res = requests.get(url, headers=GITHUB_HEADERS, params=params, timeout=10)

    if res.status_code == 403:
        print("  [경고] GitHub API 한도 초과. GITHUB_TOKEN을 .env에 추가하세요.")
        return []
    if res.status_code != 200:
        print(f"  [오류] GitHub 검색 실패: {res.status_code}")
        return []

    return res.json().get("items", [])


def get_user_info(username: str) -> dict:
    url = f"https://api.github.com/users/{username}"
    res = requests.get(url, headers=GITHUB_HEADERS, timeout=10)
    if res.status_code == 200:
        data = res.json()
        return {
            "email": data.get("email") or "",
            "bio": data.get("bio") or "",
            "twitter": data.get("twitter_username") or "",
            "blog": data.get("blog") or "",
        }
    return {"email": "", "bio": "", "twitter": "", "blog": ""}


def generate_message(repo_name: str, description: str, language: str) -> str:
    if not ANTHROPIC_KEY:
        return "[ANTHROPIC_API_KEY 없음 — .env 확인 필요]"

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Write a short, genuine outreach message to a GitHub developer.

Their project:
- Repo: {repo_name}
- Description: {description or "No description provided"}
- Language: {language or "Unknown"}

You are writing on behalf of StockMolt (stockmolt.ai).
StockMolt is an open arena where AI agents post live stock analysis,
compete on a public leaderboard, and get scored on real accuracy over time.

Message requirements:
- 3-4 sentences only
- Mention their project naturally (show you actually looked at it)
- One sentence explaining what StockMolt is
- Mention: free API, takes ~5 minutes to connect any AI model
- End with a soft question (not pushy)
- Tone: developer to developer, casual and genuine
- No subject line, no signature, just the message body

Write only the message."""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def load_sent_emails() -> set:
    if not os.path.exists(SENT_LOG):
        return set()
    with open(SENT_LOG, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def log_sent_email(email: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SENT_LOG, "a", encoding="utf-8") as f:
        f.write(email + "\n")


def send_email(to_email: str, repo_name: str, message: str) -> bool:
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = f"Your {repo_name} project + StockMolt arena"
    msg.attach(MIMEText(message, "plain"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PW)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"    발송 실패 ({to_email}): {e}")
        return False


def send_outreach_emails(results: list):
    if not GMAIL_USER or not GMAIL_APP_PW:
        print("\n[이메일] GMAIL_USER 또는 GMAIL_APP_PASSWORD 미설정 — 건너뜁니다")
        return

    sent = load_sent_emails()
    new_count = 0

    print(f"\n[4] 이메일 발송 중...")
    for r in results:
        email = r.get("email", "").strip().replace("mailto:", "")
        if not email or "@" not in email or email in sent:
            continue

        success = send_email(email, r["repo"], r["message"])
        if success:
            log_sent_email(email)
            sent.add(email)
            new_count += 1
            print(f"  ✓ {r['owner']} → {email}")
            time.sleep(5)  # 스팸 방지 딜레이

    print(f"  발송 완료: {new_count}명 (이메일 없음 또는 중복 제외)")


def run():
    print("=" * 50)
    print("StockMolt GitHub Outreach Agent")
    print("=" * 50)
    print(f"GitHub 토큰: {'있음 (5000 req/hr)' if GITHUB_TOKEN else '없음 (60 req/hr)'}")
    print(f"Anthropic API: {'있음' if ANTHROPIC_KEY else '없음'}")
    print()

    seen_owners = set()
    results = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for query in SEARCH_QUERIES:
        print(f"검색 중: '{query}'")
        repos = search_repos(query)

        for repo in repos:
            owner = repo["owner"]["login"]

            # 중복 소유자 스킵
            if owner in seen_owners:
                continue

            # 스타 수 필터
            if repo["stargazers_count"] < MIN_STARS:
                continue

            # 오래된 레포 스킵
            updated_at = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))
            if updated_at < cutoff:
                continue

            seen_owners.add(owner)

            print(f"  처리 중: {owner}/{repo['name']} ⭐{repo['stargazers_count']}")

            user_info = get_user_info(owner)
            time.sleep(0.8)

            message = generate_message(
                repo_name=repo["name"],
                description=repo.get("description", ""),
                language=repo.get("language", ""),
            )
            time.sleep(0.5)

            results.append({
                "owner": owner,
                "repo": repo["name"],
                "stars": repo["stargazers_count"],
                "language": repo.get("language", ""),
                "description": repo.get("description", ""),
                "repo_url": repo["html_url"],
                "profile_url": f"https://github.com/{owner}",
                "email": user_info["email"],
                "twitter": user_info["twitter"],
                "blog": user_info["blog"],
                "message": message,
            })

        # 쿼리 사이 대기
        time.sleep(2)

    # CSV 저장
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"outreach_{timestamp}.csv")

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    print()
    print("=" * 50)
    print(f"완료! {len(results)}명의 개발자 발견")
    print(f"저장 위치: {output_file}")
    print("=" * 50)

    # 이메일 자동 발송
    send_outreach_emails(results)

    # 상위 3개 미리보기
    print("\n[미리보기 — 상위 3명]")
    for r in results[:3]:
        print(f"\n{r['profile_url']}")
        print(f"레포: {r['repo_url']}")
        print(f"이메일: {r['email'] or '비공개'} | 트위터: {r['twitter'] or '없음'}")
        print(f"메시지:\n{r['message']}")
        print("-" * 40)


if __name__ == "__main__":
    run()
