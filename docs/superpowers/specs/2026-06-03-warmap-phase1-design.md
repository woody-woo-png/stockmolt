# War Map Phase 1 — Design Spec

**Date:** 2026-06-03  
**Status:** Approved

---

## Goal

War Map 탭을 숨김 해제하고, 기존 SVG 지도 위에 Hero 헤드라인 + Territory 카드를 추가해 첫 방문자가 3초 안에 전황을 이해할 수 있게 한다.

---

## Scope

### 추가 (신규 코드)
- **Hero 헤드라인 카드**: "🐂 BULLORIA IS WINNING" / "🐻 BEARHEIM IS WINNING" / "⚔️ CONTESTED" — `totalBull` 비율로 결정
- **Territory 카드 4개**: Crypto / US / Commodities / BondsFX 각각 점령 진영·비율·상태 표시

### 유지 (기존 코드 그대로)
- SVG 대륙 지도 (`_buildWarMapHTML` 내부 SVG 블록)
- Bull vs Bear 게이지 바
- 배틀 로그
- Supabase 데이터 fetch 로직 (`renderWarMap`)

### 활성화
- 탭 `display:none` → 제거 (nav + mobile tab 둘 다)

---

## Layout (top → bottom)

```
[Hero 헤드라인 카드]  ← 신규
[게이지 바]          ← 기존
[Territory 카드 4개] ← 신규
[SVG 대륙 지도]      ← 기존
[배틀 로그]          ← 기존
```

---

## Hero 카드 로직

| `totalBull` | 텍스트 | 색상 |
|-------------|--------|------|
| > 0.55 | 🐂 BULLORIA IS WINNING | `#3fb950` |
| < 0.45 | 🐻 BEARHEIM IS WINNING | `#f85149` |
| 0.45–0.55 | ⚔️ CONTESTED FRONT | `#e3b341` |

우측에 Bull 점령 % 숫자 표시.

---

## Territory 카드 로직

섹터별 `ratio` 값 사용 (이미 `renderWarMap`에서 계산됨):

| ratio | 배지 | 색상 |
|-------|------|------|
| > 0.6 | BULL | `#3fb950` |
| < 0.4 | BEAR | `#f85149` |
| else | CONTESTED | `#e3b341` |

표시 항목: 섹터 이름·아이콘, 진영 배지, 점령% 숫자, 24h 활동 가장 많은 섹터에 "🔥 Most active today" 표시.

섹터 목록: `WAR_SECTORS_V2` 배열 그대로 사용 (현재 Crypto, US, Commodities, BondsFX).

---

## Implementation Target

**파일 1개:** `index/index.html`

변경 위치:
1. `_buildWarMapHTMLV2` 함수 내부 HTML 생성 부분 — 맨 앞에 Hero 카드 + Territory 카드 HTML 삽입
2. `tab-warmap` div `style="display:none"` 제거
3. `mtab-warmap` div `style="display:none"` 제거

---

## Out of Scope

- Phase 2 SVG 지도 개선 (범례, 클릭 인터랙션)
- Phase 3 SNS 공유 카드
- 모바일 전용 레이아웃 최적화
