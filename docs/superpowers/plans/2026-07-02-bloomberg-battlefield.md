# Bloomberg Battlefield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 메인 게임화면의 순수 CSS 대포 애니메이션을 실시간 시장 데이터로 교체 — 탄환 비율이 브레드스를 반영하고, 좌우 SVG 패널이 스스로 그려지며 루프한다.

**Architecture:** `index.html` 단일 파일만 수정. Supabase Storage "datalab" 버킷에서 5개 JSON을 페이지 로드 후 500ms 뒤 fetch, 24h localStorage 캐시. SVG polyline + `stroke-dasharray` 애니메이션으로 draw-on 효과 구현.

**Tech Stack:** Vanilla JS, SVG, CSS animations, Supabase Storage (public bucket, no auth)

**Spec:** `docs/superpowers/specs/2026-07-02-bloomberg-battlefield-design.md`

---

## 선행 조사 결과 (읽기 전에 숙지)

- `index.html:6364` — `GM_REST`, `GM_ANON` 이미 존재. Supabase URL = `https://oyatbvqpilvbhqpiafwp.supabase.co`
- `index.html:6459–6521` — `gmStartBattle()`, `gmLoadBattleUnits()` 이미 존재. 티커 라벨 + `game_ai_pick` 연동 **이미 구현됨**. 추가 필요: 탄환 초록/빨강 방향 비율을 브레드스로 편향
- `index.html:6494` — `const fromLeft = ... : (Math.random()<0.5)` ← 이 줄만 수정하면 됨
- `index.html:2056–2057` — `#page-game > .gm-wrap` 구조. 패널은 `.gm-wrap` 바깥, `#page-game` 안에 추가
- Supabase Storage public URL 패턴: `https://oyatbvqpilvbhqpiafwp.supabase.co/storage/v1/object/public/datalab/{filename}`

---

## 파일 변경 범위

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `index.html` | CSS 추가 | `#bf-layout` grid, `.bf-panel` 패널, `.bf-badge` 배지, SVG 애니메이션, 3px 컬러바 |
| `index.html` | HTML 추가 | `#bf-layout` wrapper, `#bf-panel-left`, `#bf-panel-right`, 배지 DOM |
| `index.html` | JS 수정 | `gmStartBattle()` 내 `fromLeft` 비율 수정 |
| `index.html` | JS 추가 | `loadDatalabData()`, `applyBreadth()`, `applyDailyPulse()`, `drawEquityCurve()`, `initDataPanels()` |

신규 파일 없음. 외부 라이브러리 추가 없음.

---

## Task 1: Datalab fetch + localStorage 캐시

**Files:**
- Modify: `index.html` — JS 섹션 끝 부분 (`</script>` 직전)

- [ ] **Step 1-1: `loadDatalabData()` 함수 추가**

`index.html`의 `</script>` 직전 (약 line 7300 근처)에 아래 코드를 추가한다.

```javascript
// ── Datalab: fetch breadth/pulse/strategy_race/drawdown from Supabase Storage ──
const DATALAB_BASE = 'https://oyatbvqpilvbhqpiafwp.supabase.co/storage/v1/object/public/datalab';
const DATALAB_CACHE_KEY = 'sm_datalab_v1';
const DATALAB_CACHE_TTL = 86400000; // 24h in ms

async function loadDatalabData() {
  try {
    const cached = localStorage.getItem(DATALAB_CACHE_KEY);
    if (cached) {
      const { ts, data } = JSON.parse(cached);
      if (Date.now() - ts < DATALAB_CACHE_TTL) return data;
    }
  } catch(e) {}

  const files = ['breadth.json','daily_pulse.json','strategy_race.json','drawdown.json','index_race.json'];
  try {
    const results = await Promise.all(
      files.map(f => fetch(`${DATALAB_BASE}/${f}`).then(r => r.ok ? r.json() : null).catch(() => null))
    );
    const data = {
      breadth:      results[0],
      pulse:        results[1],
      strategyRace: results[2],
      drawdown:     results[3],
      indexRace:    results[4],
    };
    try {
      localStorage.setItem(DATALAB_CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
    } catch(e) {}
    return data;
  } catch(e) {
    return null;
  }
}
```

- [ ] **Step 1-2: 브라우저 콘솔에서 직접 테스트**

브라우저 개발자 도구 Console에서:
```javascript
loadDatalabData().then(d => console.log('breadth:', d?.breadth?.current));
```
Expected: `breadth: { pct_above_200d: <숫자>, universe: <숫자> }` 출력.  
null이면 Supabase Storage bucket이 public인지 확인: Supabase Dashboard → Storage → datalab → Settings → Public bucket 활성화.

- [ ] **Step 1-3: 캐시 동작 확인**

Console에서 한 번 더 실행:
```javascript
loadDatalabData().then(d => console.log('from cache:', d?.breadth?.current));
```
Expected: 즉시 응답 (network request 없음). DevTools Network 탭에서 fetch 요청 없는 것 확인.

- [ ] **Step 1-4: 커밋**

```bash
git add index.html
git commit -m "feat(battlefield): add loadDatalabData() with 24h localStorage cache"
```

---

## Task 2: Part C — 브레드스 비율로 탄환 방향 편향

**Files:**
- Modify: `index.html:6494`

현재 코드:
```javascript
const fromLeft = (unit && unit.dir) ? (unit.dir==='long') : (Math.random()<0.5);
```

- [ ] **Step 2-1: `gmBreadthPct` 전역 변수 추가**

`index.html:6459` 근처 (`let gmBattleTimer = null;` 바로 아래)에 추가:

```javascript
let gmBreadthPct = 50; // overridden by breadth.json; 50 = no bias
```

- [ ] **Step 2-2: `fromLeft` 계산식 수정**

`index.html:6494` 의 해당 줄을 아래로 교체:

```javascript
const fromLeft = (unit && unit.dir) ? (unit.dir==='long') : (Math.random() < gmBreadthPct / 100);
```

- [ ] **Step 2-3: `applyBreadth()` 함수 추가**

Task 1에서 추가한 `loadDatalabData()` 아래에 이어서 추가:

```javascript
function applyBreadth(breadth) {
  if (!breadth?.current) return;
  const pct = breadth.current.pct_above_200d;
  if (typeof pct !== 'number') return;
  gmBreadthPct = pct;
}
```

- [ ] **Step 2-4: 브라우저에서 수동 테스트**

Console에서:
```javascript
gmBreadthPct = 80; // 강세장 시뮬레이션
```
게임 화면에서 탄환을 관찰 — 초록(왼쪽→오른쪽) 탄환이 빨강보다 확연히 많아야 함.

```javascript
gmBreadthPct = 20; // 약세장 시뮬레이션
```
빨강 탄환이 더 많아야 함.

- [ ] **Step 2-5: 커밋**

```bash
git add index.html
git commit -m "feat(battlefield): breadth-weighted shot direction via gmBreadthPct"
```

---

## Task 3: Part C — 배지(badge) + 3px 컬러바

**Files:**
- Modify: `index.html` — CSS, HTML(`#gm-battlefield` 생성 JS), JS

- [ ] **Step 3-1: 배지 CSS 추가**

`index.html` CSS 섹션 내 `@media(max-width:760px){#gm-battlefield{display:none;}}` (line ~1858) 바로 아래에 추가:

```css
/* ── Battlefield data badges ── */
#bf-breadth-bar{position:absolute;top:0;left:0;right:0;height:3px;z-index:2;pointer-events:none;
  background:linear-gradient(90deg,#3fb950 var(--bf-pct,50%),#f85149 var(--bf-pct,50%));}
.bf-badge{position:absolute;background:rgba(13,17,23,.78);border:1px solid #ffffff14;
  border-radius:10px;padding:9px 12px;backdrop-filter:blur(6px);pointer-events:none;z-index:2;min-width:130px;}
.bf-badge-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:#6b7280;margin-bottom:3px;}
.bf-badge-val{font-size:16px;font-weight:800;}
.bf-badge-sub{font-size:10px;color:#6b7280;margin-top:2px;line-height:1.4;}
#bf-badge-breadth{left:14px;top:14px;}
#bf-badge-pulse{right:14px;top:14px;text-align:right;}
```

- [ ] **Step 3-2: 배지 DOM을 `gmStartBattle()` 내에서 생성**

`index.html:6483` — `bf.innerHTML=...` 줄을 아래로 교체:

```javascript
bf.innerHTML = `
  <div class="gm-radar g"></div>
  <div class="gm-radar r"></div>
  <div id="bf-breadth-bar"></div>
  <div class="bf-badge" id="bf-badge-breadth">
    <div class="bf-badge-lbl">Market Breadth</div>
    <div class="bf-badge-val" id="bf-bval">—</div>
    <div class="bf-badge-sub" id="bf-bsub"></div>
  </div>
  <div class="bf-badge" id="bf-badge-pulse">
    <div class="bf-badge-lbl">Daily Pulse</div>
    <div class="bf-badge-val" id="bf-pval" style="font-size:12px;color:#58a6ff">—</div>
    <div class="bf-badge-sub" id="bf-psub"></div>
  </div>`;
```

- [ ] **Step 3-3: `applyBreadth()` 함수에 DOM 업데이트 추가**

Task 2에서 작성한 `applyBreadth()` 를 아래로 교체:

```javascript
function applyBreadth(breadth) {
  if (!breadth?.current) return;
  const pct = breadth.current.pct_above_200d;
  const uni = breadth.current.universe;
  if (typeof pct !== 'number') return;
  gmBreadthPct = pct;
  const bar = document.getElementById('bf-breadth-bar');
  if (bar) bar.style.setProperty('--bf-pct', pct.toFixed(1) + '%');
  const bval = document.getElementById('bf-bval');
  const bsub = document.getElementById('bf-bsub');
  if (bval) { bval.textContent = pct.toFixed(0) + '%'; bval.style.color = pct >= 50 ? '#3fb950' : '#f85149'; }
  if (bsub && uni) bsub.textContent = 'of ' + uni + ' stocks above 200d MA';
}
```

- [ ] **Step 3-4: `applyDailyPulse()` 함수 추가**

`applyBreadth()` 아래에 추가:

```javascript
function applyDailyPulse(pulse) {
  if (!pulse?.fact) return;
  const pval = document.getElementById('bf-pval');
  const psub = document.getElementById('bf-psub');
  if (pval) pval.textContent = pulse.fact.headline || '—';
  if (psub) psub.textContent = (pulse.fact.metric || '').slice(0, 60);
}
```

- [ ] **Step 3-5: 브라우저에서 수동 테스트**

게임 화면 진입 후 Console:
```javascript
applyBreadth({ current: { pct_above_200d: 72, universe: 490 } });
```
Expected: 상단에 초록 3px 바 (72% 지점에서 빨강으로 전환), 좌상단에 `72% / of 490 stocks...` 배지 표시.

```javascript
applyDailyPulse({ fact: { headline: 'Seasonal Pattern', metric: 'July has averaged +1.8% for S&P500 over 20 years' } });
```
Expected: 우상단 배지에 내용 표시.

- [ ] **Step 3-6: 커밋**

```bash
git add index.html
git commit -m "feat(battlefield): breadth bar + data badges overlaid on battlefield"
```

---

## Task 4: Part D — 좌우 패널 레이아웃

**Files:**
- Modify: `index.html` — CSS, HTML(`#page-game` 내부 구조)

- [ ] **Step 4-1: 패널 CSS 추가**

CSS 섹션에서 `.gm-wrap{...}` (line ~1825) 바로 아래에 추가:

```css
/* ── Data panels (desktop only) ── */
#bf-layout{display:grid;grid-template-columns:230px 1fr 230px;min-height:100%;position:relative;z-index:1;}
.bf-panel{background:#111827;border-right:1px solid #1f2937;padding:16px 14px;
  display:flex;flex-direction:column;gap:10px;overflow:hidden;}
#bf-panel-right{border-right:none;border-left:1px solid #1f2937;}
.bf-panel-title{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:#4b5563;margin-bottom:4px;}
.bf-chip{background:#0d1117;border:1px solid #1f2937;border-radius:8px;padding:9px 11px;}
.bf-chip-val{font-size:17px;font-weight:800;}
.bf-chip-lbl{font-size:9px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-top:1px;}
.bf-legend{display:flex;flex-direction:column;gap:4px;margin-top:6px;}
.bf-leg{display:flex;align-items:center;gap:6px;font-size:10px;color:#9ca3af;}
.bf-leg-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
.bf-leg-dash{width:12px;height:2px;flex-shrink:0;}
.bf-chart{flex:1;min-height:160px;position:relative;}
.bf-chart svg{width:100%;height:100%;}
/* draw-on animation */
.bf-curve{fill:none;stroke-dasharray:1200;stroke-dashoffset:1200;
  animation:bfDraw var(--dur,4s) ease-out forwards, bfLoop var(--loop,16s) var(--dur,4s) linear infinite;}
@keyframes bfDraw{to{stroke-dashoffset:0;}}
@keyframes bfLoop{0%{stroke-dashoffset:0}6%{stroke-dashoffset:1200}100%{stroke-dashoffset:0}}
@media(max-width:760px){
  #bf-layout{display:block;}
  .bf-panel{display:none;}
}
```

- [ ] **Step 4-2: HTML 구조 변경**

`index.html:2056–2057`:

변경 전:
```html
<div class="page" id="page-game">
  <div class="gm-wrap">
```

변경 후:
```html
<div class="page" id="page-game">
  <div id="bf-layout">
  <div id="bf-panel-left" class="bf-panel">
    <div class="bf-panel-title">📈 S&amp;P 500 · 20yr Return</div>
    <div class="bf-chip"><div class="bf-chip-val" id="bf-sp-ret" style="color:#3fb950">—</div><div class="bf-chip-lbl">Buy &amp; Hold total return</div></div>
    <div class="bf-chart">
      <svg id="bf-svg-left" viewBox="0 0 180 160" preserveAspectRatio="none">
        <defs><linearGradient id="bf-grad-g" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#3fb950" stop-opacity=".35"/>
          <stop offset="100%" stop-color="#3fb950" stop-opacity="0"/>
        </linearGradient></defs>
        <polygon id="bf-area-left" fill="url(#bf-grad-g)" opacity=".15" points=""/>
        <polyline id="bf-line-bh" class="bf-curve" style="--dur:3.5s;--loop:15s" stroke="#3fb950" stroke-width="2" points=""/>
        <polyline id="bf-line-s1" class="bf-curve" style="--dur:5s;--loop:15s;animation-delay:1s" stroke="#58a6ff" stroke-width="1.5" stroke-dasharray="4 4" points=""/>
      </svg>
    </div>
    <div class="bf-legend">
      <div class="bf-leg"><div class="bf-leg-dot" style="background:#3fb950"></div>Buy &amp; Hold</div>
      <div class="bf-leg"><div class="bf-leg-dash" style="background:#58a6ff"></div>SMA200 strategy</div>
    </div>
    <div class="bf-chip" id="bf-chip-season"><div class="bf-chip-val" style="color:#58a6ff;font-size:13px">—</div><div class="bf-chip-lbl">Seasonality · this month</div></div>
  </div>
  <div class="gm-wrap">
```

`index.html` 에서 `</div><!-- end .gm-wrap -->` 를 찾아 아래로 교체:

```html
  </div><!-- end .gm-wrap -->
  <div id="bf-panel-right" class="bf-panel">
    <div class="bf-panel-title">📉 Drawdown · Index Race</div>
    <div class="bf-chip"><div class="bf-chip-val" id="bf-dd-val" style="color:#f85149">—</div><div class="bf-chip-lbl">S&amp;P 500 current drawdown</div></div>
    <div class="bf-chart">
      <svg id="bf-svg-right" viewBox="0 0 180 160" preserveAspectRatio="none">
        <line x1="0" y1="80" x2="180" y2="80" stroke="#ffffff08" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="3" y="76" font-size="8" fill="#4b5563">0%</text>
        <polygon id="bf-area-right" fill="url(#bf-grad-r,#f85149)" opacity=".1" points=""/>
        <polyline id="bf-line-dd1" class="bf-curve" style="--dur:4s;--loop:14s" stroke="#f85149" stroke-width="2" points=""/>
        <polyline id="bf-line-dd2" class="bf-curve" style="--dur:5.5s;--loop:14s;animation-delay:1.2s" stroke="#c4b5fd" stroke-width="1.5" stroke-dasharray="3 4" points=""/>
      </svg>
    </div>
    <div class="bf-legend">
      <div class="bf-leg"><div class="bf-leg-dot" style="background:#f85149"></div>S&amp;P 500 drawdown</div>
      <div class="bf-leg"><div class="bf-leg-dash" style="background:#c4b5fd"></div>NASDAQ drawdown</div>
    </div>
    <div class="bf-chip"><div class="bf-chip-val" id="bf-ytd-val" style="font-size:13px">—</div><div class="bf-chip-lbl">Index Race YTD</div></div>
  </div>
  </div><!-- end #bf-layout -->
```

- [ ] **Step 4-3: 레이아웃 확인**

브라우저에서 게임 탭 진입. 데스크탑(> 760px)에서:
- 좌우에 어두운 패널이 보여야 함
- 중앙에 기존 게임 카드 정상 동작 확인
- 전체 폭이 넘치지 않아야 함

모바일(< 760px)에서:
- 패널 안 보임, 기존 레이아웃 그대로

- [ ] **Step 4-4: 커밋**

```bash
git add index.html
git commit -m "feat(battlefield): left/right data panel layout (desktop grid)"
```

---

## Task 5: Part D — SVG 좌표 변환 + drawEquityCurve()

**Files:**
- Modify: `index.html` — JS 섹션

- [ ] **Step 5-1: `normalizeSvgPoints()` 헬퍼 추가**

`loadDatalabData()` 아래에 추가:

```javascript
/**
 * data_points: [[dateStr, value], ...]  (날짜 오름차순)
 * viewW, viewH: SVG viewBox 크기
 * flipY: true면 값이 클수록 위 (일반 차트), false면 값이 클수록 아래 (드로우다운)
 * returns: "x0,y0 x1,y1 ..." SVG points 문자열
 */
function normalizeSvgPoints(dataPoints, viewW, viewH, flipY) {
  if (!dataPoints || dataPoints.length < 2) return '';
  const vals = dataPoints.map(p => p[1]);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const rangeV = maxV - minV || 1;
  const n = dataPoints.length;
  return dataPoints.map((p, i) => {
    const x = (i / (n - 1)) * viewW;
    const norm = (p[1] - minV) / rangeV; // 0..1
    const y = flipY ? (1 - norm) * viewH * 0.9 + viewH * 0.05
                    : norm * viewH * 0.9 + viewH * 0.05;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function makeAreaPoints(pointsStr, viewW, viewH) {
  // 닫힌 polygon: 커브 points + 우하단 + 좌하단
  return pointsStr + ` ${viewW},${viewH} 0,${viewH}`;
}
```

- [ ] **Step 5-2: Console에서 헬퍼 테스트**

```javascript
const sample = [['2005-01',100],['2010-01',150],['2015-01',200],['2020-01',130],['2024-01',300]];
console.log(normalizeSvgPoints(sample, 180, 160, true));
// Expected: "0.0,148.5 45.0,104.5 90.0,60.5 135.0,119.3 180.0,8.5" 형태 (값 다를 수 있음)
```

- [ ] **Step 5-3: `drawLeftPanel()` 함수 추가**

```javascript
function drawLeftPanel(strategyRace) {
  if (!strategyRace?.series?.length) return;
  const bh  = strategyRace.series.find(s => s.name === 'Buy & Hold');
  const s1  = strategyRace.series.find(s => s.name && s.name !== 'Buy & Hold');
  if (!bh?.points?.length) return;

  const VW = 180, VH = 160;
  const bhPts  = normalizeSvgPoints(bh.points, VW, VH, true);
  const lineBh = document.getElementById('bf-line-bh');
  const areaL  = document.getElementById('bf-area-left');
  if (lineBh) lineBh.setAttribute('points', bhPts);
  if (areaL)  areaL.setAttribute('points', makeAreaPoints(bhPts, VW, VH));

  if (s1?.points?.length) {
    const s1Pts = normalizeSvgPoints(s1.points, VW, VH, true);
    const lineS1 = document.getElementById('bf-line-s1');
    if (lineS1) lineS1.setAttribute('points', s1Pts);
  }

  // 총 수익률 chip
  const bhVals = bh.points.map(p => p[1]);
  if (bhVals.length >= 2) {
    const ret = ((bhVals[bhVals.length-1] / bhVals[0]) - 1) * 100;
    const el = document.getElementById('bf-sp-ret');
    if (el) el.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(0) + '%';
  }

  // strategy_race에 draw-on 재시작 (points가 바뀌었으니 animation reset)
  [document.getElementById('bf-line-bh'), document.getElementById('bf-line-s1')].forEach(el => {
    if (!el) return;
    el.style.animation = 'none';
    void el.offsetWidth; // reflow
    el.style.animation = '';
  });
}
```

- [ ] **Step 5-4: `drawRightPanel()` 함수 추가**

```javascript
function drawRightPanel(drawdown, indexRace) {
  const VW = 180, VH = 160;

  // 드로우다운 커브 (값이 음수 → 0 기준선 아래)
  if (drawdown?.series?.length) {
    const sp  = drawdown.series.find(s => s.name === 'S&P500');
    const nas = drawdown.series.find(s => s.name === 'NASDAQ');

    if (sp?.points?.length) {
      // 드로우다운: 0이 최대, 음수가 아래 → flipY=false 후 반전
      const pts = normalizeSvgPoints(sp.points, VW, VH, false);
      const line = document.getElementById('bf-line-dd1');
      if (line) line.setAttribute('points', pts);

      // 현재 드로우다운 chip
      const cur = sp.points[sp.points.length - 1]?.[1];
      const el = document.getElementById('bf-dd-val');
      if (el && typeof cur === 'number') {
        el.textContent = cur === 0 ? 'ATH' : cur.toFixed(1) + '%';
        el.style.color = cur === 0 ? '#3fb950' : '#f85149';
      }
    }
    if (nas?.points?.length) {
      const pts = normalizeSvgPoints(nas.points, VW, VH, false);
      const line = document.getElementById('bf-line-dd2');
      if (line) line.setAttribute('points', pts);
    }
  }

  // Index Race YTD chip
  if (indexRace?.series?.length) {
    const today = new Date().getFullYear() + '-01-01';
    const parts = [];
    for (const s of indexRace.series) {
      const ytd = s.points?.filter(p => p[0] >= today);
      if (ytd?.length >= 2 && ytd[0][1]) {
        const chg = ((ytd[ytd.length-1][1] / ytd[0][1]) - 1) * 100;
        parts.push(`${s.name} ${chg >= 0 ? '+' : ''}${chg.toFixed(1)}%`);
      }
    }
    const el = document.getElementById('bf-ytd-val');
    if (el && parts.length) {
      el.textContent = parts.join(' · ');
      el.style.color = '#e6edf3';
      el.style.fontSize = '11px';
    }
  }

  // animation reset
  [document.getElementById('bf-line-dd1'), document.getElementById('bf-line-dd2')].forEach(el => {
    if (!el) return;
    el.style.animation = 'none';
    void el.offsetWidth;
    el.style.animation = '';
  });
}
```

- [ ] **Step 5-5: Console에서 수동 테스트 (실데이터 없는 경우)**

```javascript
const mockRace = {
  series: [
    { name: 'Buy & Hold', points: [['2005-01-01',100],['2010-01-01',155],['2015-01-01',220],['2020-01-01',280],['2024-01-01',950]] },
    { name: 'SMA200', points: [['2005-01-01',100],['2010-01-01',140],['2015-01-01',190],['2020-01-01',240],['2024-01-01',610]] }
  ]
};
drawLeftPanel(mockRace);
```
Expected: 좌측 패널 SVG에 두 개의 라인이 그려지며 draw-on 애니메이션 동작.

- [ ] **Step 5-6: 커밋**

```bash
git add index.html
git commit -m "feat(battlefield): SVG equity curve draw-on animation (left/right panels)"
```

---

## Task 6: 전체 연동 — `initDataPanels()`

**Files:**
- Modify: `index.html` — JS 섹션

- [ ] **Step 6-1: `initDataPanels()` 함수 추가 및 트리거 연결**

`drawRightPanel()` 아래에 추가:

```javascript
async function initDataPanels() {
  const data = await loadDatalabData();
  if (!data) return; // 실패 시 graceful skip — UI는 기존 그대로

  if (data.breadth)      applyBreadth(data.breadth);
  if (data.pulse)        applyDailyPulse(data.pulse);
  if (data.strategyRace) drawLeftPanel(data.strategyRace);
  if (data.drawdown || data.indexRace) drawRightPanel(data.drawdown, data.indexRace);

  // 계절성 chip (daily_pulse의 seasonality type일 때만)
  if (data.pulse?.fact?.type === 'seasonality') {
    const el = document.querySelector('#bf-chip-season .bf-chip-val');
    if (el) el.textContent = data.pulse.fact.metric?.slice(0, 30) || '—';
  }
}
```

- [ ] **Step 6-2: 게임 페이지 렌더 후 호출 연결**

`index.html`에서 `gmStartBattle(` 호출부를 찾는다 (약 line 6479, `gmStartBattle(false)` 또는 `gmStartBattle(submitted)` 형태).  
`gmStartBattle(...)` 호출 바로 아래에 추가:

```javascript
setTimeout(initDataPanels, 500); // 500ms 후 datalab fetch 시작
```

단, `setTimeout(initDataPanels, 500)` 이 중복 호출되지 않도록 `gmBattleTimer` 체크와 같은 위치에서 한 번만 실행되어야 한다.  
이미 `if(gmBattleTimer) return;` 직후에 추가하면 안전하다:

```javascript
// index.html:6485 근처
if(gmBattleTimer) return; // only the interval is single-start
setTimeout(initDataPanels, 500); // ← 여기에 추가
```

- [ ] **Step 6-3: 전체 E2E 테스트**

1. 브라우저에서 게임 탭 진입
2. DevTools Network 탭 열기
3. 진입 후 약 500ms 뒤 `breadth.json`, `daily_pulse.json`, `strategy_race.json`, `drawdown.json`, `index_race.json` fetch 요청 5개 확인
4. 좌측 패널: 초록 라인이 왼→오른쪽으로 그려지며 루프
5. 우측 패널: 빨강/보라 라인 draw-on 동작
6. 좌상단 배지: `XX% / of YYY stocks above 200d MA`
7. 우상단 배지: Daily Pulse 문구 표시
8. 상단 3px 바: 초록/빨강 비율 구분선 표시

- [ ] **Step 6-4: 실패 케이스 테스트**

DevTools Network → 요청 우클릭 → "Block request URL"로 `breadth.json` 차단 후 새로고침.  
Expected: 콘솔에 오류 없고, 패널은 빈 상태로 표시되며 게임 기능 정상 동작.

- [ ] **Step 6-5: 모바일 테스트**

DevTools → Toggle Device Toolbar (Ctrl+Shift+M) → iPhone SE 선택.  
Expected: 좌우 패널 미표시, 게임 카드 정상 동작, 배경 battlefield 숨김 (기존 동작 유지).

- [ ] **Step 6-6: 최종 커밋**

```bash
git add index.html
git commit -m "feat(battlefield): wire initDataPanels() — data-driven shots + equity curve panels complete"
```

---

## 자기 검토 결과

**스펙 커버리지 체크:**
- [x] 브레드스 비율로 탄환 방향 편향 → Task 2
- [x] 탄환에 AI 봇 픽 티커 → 기존 코드 이미 구현 (`gmLoadBattleUnits` + `game_ai_pick`)
- [x] 배지: Market Breadth % + Daily Pulse → Task 3
- [x] 3px 컬러바 → Task 3
- [x] 좌우 SVG 이퀴티 커브 + draw-on 애니메이션 → Task 4, 5
- [x] 500ms 지연 fetch → Task 6
- [x] 24h localStorage 캐시 → Task 1
- [x] fetch 실패 시 graceful fallback → Task 1 (try/catch + null return), Task 6 (`if (!data) return`)
- [x] 모바일 패널 숨김 → Task 4 CSS

**플레이스홀더 없음:** 모든 단계에 실제 코드 포함.

**타입/함수명 일관성:**
- `normalizeSvgPoints()` → Task 5-1 정의, Task 5-3/5-4 사용 ✓
- `makeAreaPoints()` → Task 5-1 정의, Task 5-3 사용 ✓
- `gmBreadthPct` → Task 2-1 정의, Task 2-2/2-3 사용 ✓
- `initDataPanels()` → Task 6-1 정의, Task 6-2 호출 ✓
