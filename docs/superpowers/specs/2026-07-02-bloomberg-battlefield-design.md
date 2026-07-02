# Bloomberg Battlefield — Design Spec
**Date:** 2026-07-02  
**Feature:** C+D 조합 — 메인화면 데이터 기반 Battlefield + 애니메이션 이퀴티 커브 패널

---

## 요약

메인 게임화면의 순수 CSS 대포 애니메이션을 **실시간 시장 데이터**로 교체한다.

- **파트 C**: 배경 탄환에 AI 봇 픽 티커(NVDA▲, TSLA▼) 붙이기 + 탄환 비율 = 시장 브레드스
- **파트 D**: 좌우에 SVG 이퀴티 커브 패널 추가 (스스로 그려지며 루프)
- 모바일은 패널 숨기고 배경 탄환만 유지 (기존과 동일)

---

## 전체 레이아웃 (데스크탑)

```
┌──────────────────────────────────────────────────────────────┐
│ [Left Panel 230px] │      Battlefield (flex:1)      │ [Right Panel 230px] │
│                    │                                │                     │
│ 📈 S&P500 20yr    │  3px 컬러바 (브레드스 비율)    │ 📉 Drawdown · YTD  │
│ SVG 커브 드로우온  │  ▲ BULL 62% │ 38% BEAR ▼      │ SVG 커브 드로우온   │
│                    │  레이더 sweep + 티커 탄환       │                     │
│ chip: +847%        │  [게임 카드 - 중앙 고정]        │ chip: -2.1% KOSPI  │
│ chip: Jul +1.8%    │                                │ chip: S&P +8.2%    │
│                    │  badge: Breadth 62%            │                     │
│                    │  badge: Daily Pulse            │                     │
└──────────────────────────────────────────────────────────────┘
```

레이아웃 변경: `#page-game` 내부를 `display:grid; grid-template-columns: 230px 1fr 230px`으로 교체.  
기존 `#gm-battlefield`는 center 컬럼 안으로 이동 (position:absolute 유지).

---

## 파트 C — 데이터 기반 Battlefield

### 탄환 티커

- **소스**: 당일 AI 봇들의 예측 픽 (`game_picks` Supabase 테이블 또는 당일 봇 결과)
- 초록 탄환 = 봇이 LONG으로 예측한 종목 (예: `NVDA▲`)
- 빨강 탄환 = 봇이 SHORT으로 예측한 종목 (예: `TSLA▼`)
- 티커 라벨은 탄환 위 `<span>`으로 함께 날아감
- 봇 픽을 불러오지 못하면 고정 fallback 목록 사용 (`["NVDA","AAPL","TSLA","META","COIN"]`)

### 탄환 비율

- `breadth.json`의 `current.pct_above_200d` 값으로 초록:빨강 발사 비율 결정
- 예: 브레드스 62% → 10초 주기 내 초록 탄환 6발 : 빨강 탄환 4발
- 기존 `fireSalvo()` 함수에 `bullCount / bearCount` 파라미터 추가

### 상단 배지 (badge)

- **좌상단**: `Market Breadth: 62%` + `of 487 stocks above 200d MA`  
  소스: `breadth.json → current.pct_above_200d`, `current.universe`
- **우상단**: Daily Pulse 한 줄 텍스트  
  소스: `daily_pulse.json → fact.metric`
- **상단 3px 컬러바**: `background: linear-gradient(90deg, #3fb950 {pct}%, #f85149 {pct}%)`

---

## 파트 D — 이퀴티 커브 패널

### 왼쪽 패널 — S&P500 Strategy Race

| 요소 | 내용 |
|------|------|
| 제목 | `📈 S&P 500 · 20yr Return` |
| SVG 커브 1 | Buy & Hold 누적 수익선 (초록, 실선) |
| SVG 커브 2 | SMA200 전략 수익선 (파란, 점선) |
| 애니메이션 | `stroke-dasharray` draw-on → 3.5s에 완성 → 2s 정지 → 리셋 루프 |
| 상단 chip | `+847%` / `buy & hold · 20 years` |
| 하단 chip | `Jul avg +1.8%` / `20yr seasonality` (daily_pulse seasonality 값) |
| 데이터 | `strategy_race.json → series[0].points` (Buy&Hold), `series[1].points` (SMA200) |

**SVG 좌표 변환**: `points` 배열의 날짜/값을 SVG viewBox `0 0 180 160`으로 정규화.  
X축: 날짜 → 0~180 선형. Y축: 최소값~최대값 → 160~0 반전.

### 오른쪽 패널 — Drawdown & Index Race

| 요소 | 내용 |
|------|------|
| 제목 | `📉 Drawdown · Index Race` |
| SVG 커브 1 | KOSPI 드로우다운 (빨강, 실선) |
| SVG 커브 2 | KOSDAQ 드로우다운 (보라, 점선) |
| 기준선 | Y=0 기준 수평 점선 (`0%` 텍스트) |
| 애니메이션 | 동일 draw-on 루프 (4s 완성) |
| 상단 chip | 현재 KOSPI 드로우다운 수치 |
| 하단 chip | S&P500 YTD (`index_race.json`) |
| 데이터 | `drawdown.json → series`, `index_race.json → series` |

---

## 데이터 흐름

```
Real_stock_bot/data_collector/upload_supabase.py
  → run_all() 매일 실행 (기존 cron 유지)
  → Supabase Storage bucket "datalab"
      ├── breadth.json
      ├── daily_pulse.json
      ├── strategy_race.json
      ├── drawdown.json
      └── index_race.json

index.html (페이지 로드 시)
  1. 게임 카드 렌더 완료
  2. 500ms delay
  3. Promise.all([
       fetch(SUPABASE_URL/storage/v1/object/public/datalab/breadth.json),
       fetch(...daily_pulse.json),
       fetch(...strategy_race.json),
       fetch(...drawdown.json),
       fetch(...index_race.json),
     ])
  4. localStorage 캐시 저장 (key: "datalab_cache", TTL: 24h)
  5. 캐시 있으면 fetch 생략, 캐시 데이터 즉시 사용
  6. UI 업데이트:
     - applyBreadth(breadth)
     - applyPulse(pulse)
     - drawEquityCurve('left', strategyRace)
     - drawEquityCurve('right', drawdown, indexRace)
     - updateBattlefield(breadth, botPicks)
```

### 봇 픽 연동

- `updateBattlefield(breadth, botPicks)` 호출 전 현재 날짜 AI 픽을 Supabase `game_picks` 테이블에서 조회
- 쿼리: `select ticker, direction from game_picks where game_date = today AND is_bot = true`
- LONG 픽 → 초록 탄환 티커 목록, SHORT 픽 → 빨강 탄환 티커 목록
- 봇 픽이 없으면 fallback: `{ long: ["NVDA","AAPL","META"], short: ["TSLA","COIN"] }`

---

## 에러 핸들링

| 상황 | 처리 |
|------|------|
| fetch 실패 | 콘솔 경고만, UI는 기존 순수 CSS 애니메이션 그대로 유지 |
| 캐시 만료 전 | 캐시 데이터 사용, 백그라운드 재fetch 없음 (다음 로드 때 갱신) |
| SVG 데이터 없음 | 패널 자체를 `display:none` (빈 패널 표시 안 함) |
| 봇 픽 없음 | fallback 티커 목록 사용 |

---

## 파일 변경 범위

| 파일 | 변경 내용 |
|------|-----------|
| `index.html` | CSS: 레이아웃 grid, 패널 스타일, SVG 애니메이션, badge 스타일 |
| `index.html` | HTML: 좌우 패널 DOM, badge DOM, 상단 컬러바 DOM 추가 |
| `index.html` | JS: `loadDatalabData()`, `applyBreadth()`, `drawEquityCurve()`, `updateBattlefield()` 함수 추가, 기존 `fireSalvo()` 수정 |

신규 파일 없음. 외부 라이브러리 추가 없음 (순수 SVG + CSS).

---

## 모바일 처리

```css
@media (max-width: 760px) {
  .data-panel { display: none; }
  /* 기존 #gm-battlefield { display:none } 그대로 유지 */
  #page-game { grid-template-columns: 1fr; }
}
```

---

## 성공 기준

- [ ] 페이지 로드 후 500ms 내 데이터 fetch 시작
- [ ] 좌우 SVG 커브가 그려지며 루프됨
- [ ] 탄환에 AI 봇 픽 티커 라벨 표시
- [ ] 초록/빨강 탄환 비율이 브레드스 데이터와 일치
- [ ] 데이터 fetch 실패 시 기존 순수 애니메이션으로 graceful fallback
- [ ] 모바일에서 패널 미표시, 성능 저하 없음
- [ ] 24h localStorage 캐시 동작 확인
