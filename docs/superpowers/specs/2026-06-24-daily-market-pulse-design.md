# Daily Market Pulse Card — 설계

작성: 2026-06-24 · 키르/지크

## 목적

Real_stock_bot에 매일 쌓이는 20년 일봉 데이터(734종목 + 주요 지수)를 **하루 한 장짜리 카드**로 가공해 stockmolt.ai 메인 랜딩 상단에 노출한다.
목적은 **입소문(word-of-mouth) 기반 신규 유저 유입**이다.
카드는 비로그인 방문자도 바로 볼 수 있고, 공유 시 시장 팩트 + 링크가 함께 나가도록 설계한다.

## 핵심 가설

- 날짜가 찍힌 "오늘의 시장 사실" + "지금 몇 명이 BULL/BEAR" 조합이 공유 욕구를 자극한다
- 공유 텍스트에 링크가 포함되면 클릭 → 랜딩 → 게임 참여로 이어지는 단순 깔때기가 만들어진다
- 팩트가 매일 바뀌면 재방문 루틴이 생기고, 공유도 반복된다

## 바이럴 루프

```
유저 → 카드 공유(X/클립보드)
  → 친구 클릭 → 랜딩 진입 → 카드 확인
  → [Join the prediction →] → 게임 참여
  → 다음 날 또 공유
```

## 카드 구조 (UI)

```
┌────────────────────────────────────────────────┐
│  📊 Market Pulse · June 24, 2026               │
│                                                │
│  Market Health                                 │
│  61% of 734 stocks are above their            │
│  200-day moving average                        │
│                                                │
│  Historically at this level, markets rose      │
│  3 months later — 68% of the time             │
│  (based on 20 years of data)                   │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │  🎮 Today's Players                      │  │
│  │  1,247 predictions · 63% going BULL 🐂   │  │
│  │  Yesterday: 71% predicted correctly      │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  [Join the prediction →]    [Share on 𝕏]      │
└────────────────────────────────────────────────┘
```

## 데이터 소스 (두 갈래)

| 레이어 | 출처 | 갱신 주기 |
|---|---|---|
| 시장 팩트 | Real_stock_bot → `daily_pulse.json` → Supabase Storage `datalab` 버킷 | 매일 07:00 자동 |
| 플레이어 현황 | Supabase `predictions` 테이블 집계 (anon key, 공개) | 실시간 fetch |

## 팩트 로테이션 (날짜 기반)

`date_index = (date - epoch).days % 5` 로 매일 하나를 선택.

| index | 팩트 유형 | 핵심 숫자 | 20년 맥락 문구 |
|---|---|---|---|
| 0 | Market Health | 734종목 중 N% > 200일선 | "At this breadth level, markets rose 3 months later X% of the time" |
| 1 | Seasonality | 이번 달 S&P500 역사 평균 수익률 | "June has averaged +X% for S&P500 over 20 years" |
| 2 | Drawdown | S&P500 현재 고점 대비 낙폭 | "The deepest drawdown in 20 years was -56.8% (2009)" |
| 3 | Strategy Graveyard | 전략 중 보유 초과 달성 수 | "Only 1 of 99 strategies beat simple buy & hold over 20 years" |
| 4 | Index Race | YTD 지수 비교 | "S&P500 +14% YTD vs KOSPI +3% — same period 20 years tracked" |

## 공유 텍스트 (자동 생성)

```
📊 [팩트 핵심 숫자 + 한 줄 설명]
[20년 맥락 문구]

[N] players are predicting today's market on stockmolt.
Are you in? → stockmolt.ai
```

버튼 두 개: X intent URL 열기 / 클립보드 복사.

## `daily_pulse.json` 구조

```json
{
  "generated_at": "2026-06-24T07:00:00Z",
  "date": "2026-06-24",
  "fact_index": 0,
  "fact": {
    "type": "breadth",
    "headline": "Market Health",
    "metric": "61% of 734 stocks above 200-day MA",
    "context": "At this breadth level, markets rose 3 months later — 68% of the time over 20 years",
    "share_text": "📊 61% of 734 stocks are above their 200-day average.\nAt this breadth level, markets rose 3 months later — 68% of the time.\n\nAre you in? → stockmolt.ai"
  }
}
```

## 아키텍처 / 데이터 흐름

```
[Real_stock_bot]
  data_collector/datalab.py
    build_daily_pulse(db_path) → dict
      └─ fact_index = (today - epoch).days % 5
      └─ 해당 팩트 계산 (breadth / seasonality / drawdown / graveyard / index_race)
      └─ share_text 생성
  data_collector/upload_supabase.py
    → Supabase Storage "datalab/daily_pulse.json" 업로드 (SERVICE_KEY)

[stockmolt index.html]
  fetch("${SUPABASE_URL}/storage/v1/object/public/datalab/daily_pulse.json")
  fetch predictions aggregate (anon key)
    SELECT COUNT(*),
           SUM(CASE WHEN direction='bullish' THEN 1 ELSE 0 END)::float / COUNT(*) * 100
    FROM predictions
    WHERE created_at >= CURRENT_DATE AND created_at < CURRENT_DATE + INTERVAL '1 day'
  → 카드 렌더 (바닐라 JS, 기존 패턴 유지)
  → Share 버튼: X intent / 클립보드
```

## 배치 위치

- `index.html` 메인 랜딩 상단 — 게임 섹션 위
- 비로그인 방문자도 전체 카드 노출 (fetch 인증 불필요)
- 모바일 대응: 단일 컬럼, 풀 너비

## 모듈 변경 범위

### Real_stock_bot

- `data_collector/datalab.py` — `build_daily_pulse(db_path)` 추가
  - 5가지 팩트 함수 각각 구현 (breadth·seasonality·drawdown·graveyard·index_race는 기존 함수 재활용)
  - `share_text` 문자열 생성 포함
- `data_collector/upload_supabase.py` — `daily_pulse.json` 업로드 경로 추가
- 스케줄러: 기존 07:00 수집 후 `daily_pulse.json` 재생성·업로드

### stockmolt

- `index.html`
  - 랜딩 상단에 `#daily-pulse` 섹션 추가
  - `renderDailyPulse()` JS 함수 (fetch × 2 → 카드 렌더)
  - Share 버튼 핸들러

## 안전 원칙

- 팩트는 집계·중립 (개별 종목 추천 없음)
- `share_text`에 "financial advice" 표현 없음
- `daily_pulse.json`은 공개 버킷 읽기 — SERVICE_KEY는 업로드 측(Real_stock_bot)에만 존재, 프론트 노출 없음

## 단계

- **Phase 1** — `build_daily_pulse()` 구현 + `daily_pulse.json` 생성·업로드·stockmolt 카드 렌더 → 배포 확인
- **Phase 2** — 스케줄러 연결 (매일 07:00 자동 갱신)

## 테스트

- `test_dc_datalab.py` — `build_daily_pulse()` 5가지 팩트 각각 구조·값 검증 (DB 픽스처 사용)
- `test_dc_upload_supabase.py` — `daily_pulse.json` 업로드 경로 검증 (`put_fn` 주입)
- 프론트: 로컬 `index.html` + 샘플 JSON으로 수동 확인 → 배포
