# Daily Market Pulse Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 자동 갱신되는 "오늘의 시장 팩트 카드"를 stockmolt 게임 페이지 최상단에 추가해 공유 → 신규 유저 유입 루프를 만든다.

**Architecture:** Real_stock_bot `datalab.py`에 `build_daily_pulse()`를 추가해 날짜 기반으로 5가지 팩트 중 하나를 계산하고, `upload_supabase.py`의 `run_all()`이 `daily_pulse.json`을 Supabase Storage에 업로드한다. stockmolt `index.html` 게임 페이지 최상단에 카드 HTML을 추가하고, `renderDailyPulse()`가 JSON + predictions 집계를 fetch해 렌더링한다. 공유 버튼은 X(트위터) intent URL을 열어 바이럴 루프를 만든다.

**Tech Stack:** Python (datalab.py, upload_supabase.py, pytest), Vanilla JS, Supabase Storage (public bucket `datalab`), Supabase REST API

---

## File Map

| 파일 | 변경 유형 | 책임 |
|---|---|---|
| `C:\Users\amire\AI\Real_stock_bot\data_collector\datalab.py` | 수정 | `build_daily_pulse()` + 5개 helper 추가 |
| `C:\Users\amire\AI\Real_stock_bot\data_collector\upload_supabase.py` | 수정 | `run_all()`에 `daily_pulse.json` 추가 |
| `C:\Users\amire\AI\Real_stock_bot\tests\test_dc_datalab.py` | 수정 | `build_daily_pulse` 테스트 추가 |
| `C:\Users\amire\AI\Real_stock_bot\tests\test_dc_upload_supabase.py` | 수정 | `test_run_all_uploads_five_datasets` → 6개로 업데이트 |
| `c:\Users\amire\AI\stockmolt\index.html` | 수정 | `#daily-pulse` 카드 HTML + JS 추가 |

---

## Task 1: `build_daily_pulse()` 구현 (datalab.py)

**Files:**
- Modify: `C:\Users\amire\AI\Real_stock_bot\data_collector\datalab.py`
- Test: `C:\Users\amire\AI\Real_stock_bot\tests\test_dc_datalab.py`

- [ ] **Step 1-1: 실패 테스트 작성**

`tests/test_dc_datalab.py` 맨 아래에 추가:

```python
def test_build_daily_pulse_returns_required_keys(monkeypatch):
    from datetime import date
    from data_collector import datalab, queries, scanner

    dates = [f"20{y:02d}-{m:02d}-28" for y in range(5, 8) for m in range(1, 13)]
    closes = [100 + i * 0.5 for i in range(len(dates))]
    rows = [(d, 0, 0, 0, c, 0) for d, c in zip(dates, closes)]
    monkeypatch.setattr(queries, "prices_range", lambda db, sym, start=None, end=None: rows)
    monkeypatch.setattr(scanner, "scan", lambda db, **kw: [{"beats_buyhold": False}] * 3)
    monkeypatch.setattr(datalab, "_breadth_universe", lambda db: ["AAA"])

    out = datalab.build_daily_pulse("x.db", today=date(2026, 1, 1))
    assert "generated_at" in out
    assert "date" in out
    assert "fact_index" in out
    assert "fact" in out
    fact = out["fact"]
    assert all(k in fact for k in ("type", "headline", "metric", "context", "share_text"))


def test_build_daily_pulse_rotates_all_5(monkeypatch):
    from datetime import date
    from data_collector import datalab, queries, scanner
    from data_collector.datalab import _PULSE_EPOCH

    dates = [f"20{y:02d}-{m:02d}-28" for y in range(5, 8) for m in range(1, 13)]
    closes = [100 + i * 0.5 for i in range(len(dates))]
    rows = [(d, 0, 0, 0, c, 0) for d, c in zip(dates, closes)]
    monkeypatch.setattr(queries, "prices_range", lambda db, sym, start=None, end=None: rows)
    monkeypatch.setattr(scanner, "scan", lambda db, **kw: [{"beats_buyhold": False}] * 3)
    monkeypatch.setattr(datalab, "_breadth_universe", lambda db: ["AAA"])

    types = set()
    for i in range(5):
        d = date.fromordinal(_PULSE_EPOCH.toordinal() + i)
        out = datalab.build_daily_pulse("x.db", today=d)
        types.add(out["fact"]["type"])
    assert types == {"breadth", "seasonality", "drawdown", "graveyard", "index_race"}
```

- [ ] **Step 1-2: 테스트 실패 확인**

```
cd C:\Users\amire\AI\Real_stock_bot
python -m pytest tests/test_dc_datalab.py::test_build_daily_pulse_returns_required_keys -v
```
Expected: `ERROR` 또는 `FAILED` (함수 없음)

- [ ] **Step 1-3: `datalab.py` 하단에 구현 추가**

`data_collector/datalab.py` 파일 맨 아래에 다음 코드 추가:

```python
# ─────────── Daily Market Pulse ───────────
from calendar import month_name as _month_name
from datetime import date as _date

_PULSE_EPOCH = _date(2026, 1, 1)


def _pulse_breadth(db_path):
    data = build_breadth(db_path)
    pct = data["current"]["pct_above_200d"]
    universe = data["current"]["universe"]
    if pct is None:
        return {"type": "breadth", "headline": "Market Health",
                "metric": "Breadth data unavailable", "context": "",
                "share_text": "Can you predict today's market? → stockmolt.ai"}
    metric = f"{pct:.0f}% of {universe} stocks are above their 200-day average"
    context = "Based on 20 years of daily market breadth data"
    share_text = (f"📊 {metric}.\n{context}.\n\n"
                  "Can you predict today's market? → stockmolt.ai")
    return {"type": "breadth", "headline": "Market Health",
            "metric": metric, "context": context, "share_text": share_text}


def _pulse_seasonality(db_path):
    today = _date.today()
    data = build_seasonality(db_path)
    avg = data["avg_by_month"][today.month - 1]
    mname = _month_name[today.month]
    if avg is None:
        return {"type": "seasonality", "headline": "Seasonal Pattern",
                "metric": f"No data for {mname}", "context": "",
                "share_text": f"Can you predict this {mname}? → stockmolt.ai"}
    sign = "+" if avg >= 0 else ""
    metric = f"{mname} has averaged {sign}{avg:.1f}% for S&P500 over 20 years"
    context = "Based on monthly S&P500 returns since 2005"
    share_text = (f"📊 {metric}.\n{context}.\n\n"
                  f"Can you predict this {mname}? → stockmolt.ai")
    return {"type": "seasonality", "headline": "Seasonal Pattern",
            "metric": metric, "context": context, "share_text": share_text}


def _pulse_drawdown(db_path):
    data = build_drawdown(db_path)
    sp = next((s for s in data["series"] if s["name"] == "S&P500"), None)
    if not sp or not sp["points"]:
        return {"type": "drawdown", "headline": "Market Depth",
                "metric": "Drawdown data unavailable", "context": "",
                "share_text": "Can you predict today's market? → stockmolt.ai"}
    current_dd = sp["points"][-1][1]
    worst_dd = min(p[1] for p in sp["points"])
    metric = ("S&P500 is at its all-time high" if current_dd == 0.0
              else f"S&P500 is {abs(current_dd):.1f}% below its all-time high")
    context = f"Deepest drawdown in 20 years: {worst_dd:.1f}% (2009)"
    share_text = (f"📊 {metric}.\n{context}.\n\n"
                  "Can you predict the next move? → stockmolt.ai")
    return {"type": "drawdown", "headline": "Market Depth",
            "metric": metric, "context": context, "share_text": share_text}


def _pulse_graveyard(db_path):
    data = build_strategy_race(db_path)
    total = data["summary"]["total"]
    beat = data["summary"]["beat_buyhold"]
    metric = f"Only {beat} of {total} strategies beat buy & hold"
    context = "Tested across S&P500 universe over ~20 years"
    share_text = (f"📊 {metric} over 20 years.\n{context}.\n\n"
                  "Think you can beat the market? → stockmolt.ai")
    return {"type": "graveyard", "headline": "Strategy Graveyard",
            "metric": metric, "context": context, "share_text": share_text}


def _pulse_index_race(db_path):
    data = build_index_race(db_path)
    ytd_start = f"{_date.today().year}-01-01"
    parts = []
    for s in data["series"]:
        ytd_pts = [p for p in s["points"] if p[0] >= ytd_start]
        if len(ytd_pts) >= 2 and ytd_pts[0][1]:
            chg = round((ytd_pts[-1][1] / ytd_pts[0][1] - 1) * 100, 1)
            parts.append(f"{s['name']} {chg:+.1f}%")
    if not parts:
        return {"type": "index_race", "headline": "Index Race YTD",
                "metric": "Index data unavailable", "context": "",
                "share_text": "Can you predict today's market? → stockmolt.ai"}
    metric = " · ".join(parts)
    context = "Year-to-date performance, normalized from Jan 1"
    share_text = (f"📊 YTD: {metric}.\n{context}.\n\n"
                  "Can you predict today's winner? → stockmolt.ai")
    return {"type": "index_race", "headline": "Index Race YTD",
            "metric": metric, "context": context, "share_text": share_text}


_PULSE_BUILDERS = [
    _pulse_breadth,
    _pulse_seasonality,
    _pulse_drawdown,
    _pulse_graveyard,
    _pulse_index_race,
]


def build_daily_pulse(db_path, today=None):
    """오늘의 시장 팩트 카드.

    반환: {generated_at, date, fact_index, fact:{type, headline, metric, context, share_text}}
    """
    today = today or _date.today()
    idx = (today - _PULSE_EPOCH).days % 5
    fact = _PULSE_BUILDERS[idx](db_path)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": today.isoformat(),
        "fact_index": idx,
        "fact": fact,
    }
```

- [ ] **Step 1-4: 테스트 통과 확인**

```
python -m pytest tests/test_dc_datalab.py -v -k "pulse"
```
Expected: 2개 PASSED

- [ ] **Step 1-5: 전체 테스트 회귀 확인**

```
python -m pytest tests/test_dc_datalab.py -v
```
Expected: 전체 PASSED (기존 7개 + 신규 2개)

- [ ] **Step 1-6: 커밋**

```
cd C:\Users\amire\AI\Real_stock_bot
git add data_collector/datalab.py tests/test_dc_datalab.py
git commit -m "feat(datalab): build_daily_pulse — 5가지 일별 회전 팩트 카드"
```

---

## Task 2: `run_all()`에 daily_pulse.json 추가

**Files:**
- Modify: `C:\Users\amire\AI\Real_stock_bot\data_collector\upload_supabase.py`
- Test: `C:\Users\amire\AI\Real_stock_bot\tests\test_dc_upload_supabase.py`

- [ ] **Step 2-1: 기존 테스트 수정 (5개 → 6개)**

`tests/test_dc_upload_supabase.py`의 `test_run_all_uploads_five_datasets` 함수를 아래로 교체:

```python
def test_run_all_uploads_six_datasets(monkeypatch):
    uploaded = []
    monkeypatch.setattr(up, "upload_json", lambda name, obj, **kw: uploaded.append(name))
    from data_collector import datalab
    for fn in ("build_strategy_race", "build_breadth", "build_drawdown",
               "build_seasonality", "build_index_race", "build_daily_pulse"):
        monkeypatch.setattr(datalab, fn, lambda db: {"x": 1})
    up.run_all(db_path="x")
    assert set(uploaded) == {
        "strategy_race.json", "breadth.json", "drawdown.json",
        "seasonality.json", "index_race.json", "daily_pulse.json",
    }
```

- [ ] **Step 2-2: 테스트 실패 확인**

```
python -m pytest tests/test_dc_upload_supabase.py::test_run_all_uploads_six_datasets -v
```
Expected: FAILED (daily_pulse.json 없음)

- [ ] **Step 2-3: `run_all()` 수정**

`upload_supabase.py`의 `run_all()` 함수에서 `datasets` dict에 한 줄 추가:

```python
def run_all(db_path=None):
    """6종 데이터셋 생성·업로드. 반환: {파일명: 결과}."""
    db_path = db_path or config.DB_PATH
    datasets = {
        "strategy_race.json": datalab.build_strategy_race,
        "breadth.json": datalab.build_breadth,
        "drawdown.json": datalab.build_drawdown,
        "seasonality.json": datalab.build_seasonality,
        "index_race.json": datalab.build_index_race,
        "daily_pulse.json": datalab.build_daily_pulse,   # ← 추가
    }
    out = {}
    for name, fn in datasets.items():
        out[name] = upload_json(name, fn(db_path))
    return out
```

- [ ] **Step 2-4: 테스트 통과 확인**

```
python -m pytest tests/test_dc_upload_supabase.py -v
```
Expected: 전체 PASSED

- [ ] **Step 2-5: 커밋**

```
git add data_collector/upload_supabase.py tests/test_dc_upload_supabase.py
git commit -m "feat(upload): run_all에 daily_pulse.json 추가"
```

---

## Task 3: stockmolt 게임 페이지에 카드 HTML 추가

**Files:**
- Modify: `c:\Users\amire\AI\stockmolt\index.html`

- [ ] **Step 3-1: `#daily-pulse` 카드 HTML 삽입**

`index.html`에서 아래 문자열을 찾는다:

```html
  <div class="page" id="page-game">
    <div class="gm-wrap">
      <div class="gm-card" style="display:flex;align-items:center;justify-content:center;gap:14px;padding:9px 12px;cursor:pointer;font-size:13px;" onclick="goPage('datalab')">
```

그 바로 앞(= `<div class="gm-wrap">` 바로 다음)에 다음 HTML을 삽입:

```html
      <div id="daily-pulse" class="gm-card" style="padding:0;overflow:hidden;">
        <div style="padding:14px 16px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:11px;font-weight:700;color:#8b949e;text-transform:uppercase;letter-spacing:.8px;" id="dp-headline">📊 Market Pulse</span>
            <span style="font-size:11px;color:#6e7681;" id="dp-date"></span>
          </div>
          <div style="font-size:16px;font-weight:800;color:#e6edf3;margin-bottom:6px;line-height:1.3;" id="dp-metric">Loading…</div>
          <div style="font-size:12px;color:#8b949e;margin-bottom:12px;" id="dp-context"></div>
          <div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px 12px;margin-bottom:12px;">
            <div style="font-size:11px;font-weight:700;color:#58a6ff;margin-bottom:2px;">🎮 Today's Players</div>
            <div style="font-size:13px;color:#e6edf3;" id="dp-players-stat">Loading…</div>
          </div>
          <div style="display:flex;gap:8px;">
            <button onclick="document.getElementById('gm-picks').scrollIntoView({behavior:'smooth'})" style="flex:1;background:#238636;border:none;border-radius:8px;padding:9px 12px;color:#fff;font-size:12px;font-weight:700;cursor:pointer;">Join the prediction →</button>
            <button onclick="dpShare()" style="background:#21262d;border:1px solid #30363d;border-radius:8px;padding:9px 14px;color:#8b949e;font-size:12px;font-weight:700;cursor:pointer;">Share 𝕏</button>
          </div>
        </div>
      </div>
```

삽입 위치 정확히: `<div class="gm-wrap">` 여는 태그 바로 다음 줄.

- [ ] **Step 3-2: 브라우저로 HTML 구조 확인**

`index.html`을 브라우저에서 열어 게임 페이지 최상단에 "Loading…" 카드가 보이는지 확인. 아직 JS가 없으므로 "Loading…" 텍스트가 보여야 정상.

---

## Task 4: `renderDailyPulse()` JS 구현 + goPage 연결

**Files:**
- Modify: `c:\Users\amire\AI\stockmolt\index.html`

- [ ] **Step 4-1: `renderDailyPulse()` + `dpShare()` 함수 추가**

`index.html`에서 `renderDataLab` 함수 선언 바로 위를 찾아 다음 JS를 삽입한다.
(`async function renderDataLab()` 줄 바로 앞)

```javascript
    let _dpShareText = '';

    async function renderDailyPulse() {
      const metricEl = document.getElementById('dp-metric');
      const contextEl = document.getElementById('dp-context');
      const headlineEl = document.getElementById('dp-headline');
      const dateEl = document.getElementById('dp-date');
      const statsEl = document.getElementById('dp-players-stat');
      if (!metricEl) return;

      try {
        const today = new Date().toISOString().split('T')[0];
        const [pulseRes, predsRes] = await Promise.all([
          fetch(`${SUPABASE_URL}/storage/v1/object/public/datalab/daily_pulse.json`),
          fetch(
            `${SUPABASE_URL}/rest/v1/predictions?select=direction&created_at=gte.${today}T00%3A00%3A00Z&limit=9999`,
            { headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` } }
          )
        ]);

        const pulse = await pulseRes.json();
        const preds = await predsRes.json();

        // 팩트 렌더
        const fact = pulse.fact;
        const dateStr = new Date(pulse.date + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        if (headlineEl) headlineEl.textContent = `📊 ${fact.headline}`;
        if (dateEl) dateEl.textContent = dateStr;
        if (metricEl) metricEl.textContent = fact.metric;
        if (contextEl) contextEl.textContent = fact.context;

        // 플레이어 통계
        const total = Array.isArray(preds) ? preds.length : 0;
        const bullish = Array.isArray(preds) ? preds.filter(p => p.direction === 'bullish').length : 0;
        const bullPct = total > 0 ? Math.round(bullish / total * 100) : null;
        if (statsEl) {
          if (total === 0) {
            statsEl.textContent = 'Be the first to predict today!';
          } else {
            const color = bullPct >= 50 ? '#3fb950' : '#f85149';
            const side = bullPct >= 50 ? 'BULL 🐂' : 'BEAR 🐻';
            statsEl.innerHTML = `<b style="color:#e6edf3">${total.toLocaleString()}</b> predictions · <b style="color:${color}">${bullPct}% going ${side}</b>`;
          }
        }

        // 공유 텍스트 조립
        const playerLine = total > 0
          ? `\n\n${total.toLocaleString()} players are predicting today — ${bullPct}% going BULL 🐂`
          : '';
        _dpShareText = `${fact.share_text}${playerLine}`;

      } catch (e) {
        if (metricEl) metricEl.textContent = 'Market data unavailable';
        if (statsEl) statsEl.textContent = '–';
      }
    }

    function dpShare() {
      if (!_dpShareText) return;
      const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(_dpShareText)}`;
      window.open(url, '_blank', 'noopener');
    }

```

- [ ] **Step 4-2: `goPage('game')` 에 `renderDailyPulse()` 연결**

`index.html`에서 아래 줄을 찾는다:

```javascript
      if (page === 'game' && typeof renderGame === 'function') renderGame();
```

그 바로 다음 줄에 추가:

```javascript
      if (page === 'game') renderDailyPulse();
```

- [ ] **Step 4-3: 로컬에서 샘플 JSON으로 동작 확인**

로컬 테스트용 임시 방법: 브라우저 콘솔에서 직접 확인한다.

1. `index.html`을 브라우저에서 연다
2. 콘솔에서 실행:
```javascript
// 임시: fetch를 모킹해 실제 네트워크 없이 확인
const orig = window.fetch;
window.fetch = async (url, ...args) => {
  if (url.includes('daily_pulse.json')) {
    return { json: async () => ({
      date: '2026-06-24',
      fact: {
        type: 'breadth',
        headline: 'Market Health',
        metric: '61% of 734 stocks are above their 200-day average',
        context: 'Based on 20 years of daily market breadth data',
        share_text: '📊 61% of 734 stocks above 200-day average.\n\nCan you predict today? → stockmolt.ai'
      }
    })}
  }
  return orig(url, ...args);
};
renderDailyPulse();
```
3. 카드에 "Market Health", "61% of 734 stocks…", 날짜가 표시되는지 확인
4. "Share 𝕏" 버튼 클릭 시 X 팝업이 열리는지 확인
5. `window.fetch = orig;` 로 모킹 해제

- [ ] **Step 4-4: 커밋**

```
cd c:\Users\amire\AI\stockmolt
git add index.html
git commit -m "feat(pulse): Daily Market Pulse 카드 — 게임 페이지 최상단, 공유 버튼"
```

---

## Task 5: 실제 JSON 생성 + Supabase 업로드 + 라이브 확인

**Files:**
- `C:\Users\amire\AI\Real_stock_bot` 에서 실행

- [ ] **Step 5-1: `daily_pulse.json` 로컬 생성 확인**

```python
# C:\Users\amire\AI\Real_stock_bot 에서 실행
python -c "
from data_collector import datalab, config
import json
out = datalab.build_daily_pulse(config.DB_PATH)
print(json.dumps(out, indent=2, ensure_ascii=False))
"
```
Expected: fact_index, fact.type, fact.metric 등 정상 출력. `metric`에 실제 숫자가 포함돼야 함.

- [ ] **Step 5-2: Supabase 업로드**

```
cd C:\Users\amire\AI\Real_stock_bot
python -m data_collector.upload_supabase
```
Expected: `{"strategy_race.json": {"ok": True}, ..., "daily_pulse.json": {"ok": True}, ...}` 출력

- [ ] **Step 5-3: 라이브 fetch 확인**

브라우저에서 아래 URL이 응답하는지 확인 (탭에서 직접 열기):
```
https://oyatbvqpilvbhqpiafwp.supabase.co/storage/v1/object/public/datalab/daily_pulse.json
```
Expected: JSON 응답, `fact.metric`에 오늘 날짜 기반 팩트 텍스트 확인

- [ ] **Step 5-4: stockmolt 로컬에서 카드 동작 확인**

`index.html`을 브라우저로 열어 게임 페이지에서:
1. 상단 카드에 오늘 날짜 + 실제 팩트 숫자가 보이는지 확인
2. "Today's Players" 섹션에 예측 수가 표시되는지 확인 (0명이면 "Be the first to predict today!" 표시)
3. "Share 𝕏" 클릭 시 트위터 팝업에 share_text가 올바르게 들어가는지 확인

- [ ] **Step 5-5: Cloudflare 배포**

```
cd c:\Users\amire\AI\stockmolt
git push origin main
```
Cloudflare Pages 자동 배포 후 https://stockmolt.ai 에서 카드 확인.

---

## Self-Review

**Spec coverage 체크:**
- ✅ 매일 자동 갱신 팩트 (5가지 로테이션 → `build_daily_pulse`)
- ✅ 플레이어 현황 (predictions 집계 → `renderDailyPulse`)
- ✅ 공유 버튼 (X intent URL → `dpShare`)
- ✅ 메인 랜딩(게임 페이지) 상단 배치 (gm-wrap 첫 번째 카드)
- ✅ 비로그인 노출 (공개버킷 + anon key)
- ✅ 날짜 기반 로테이션 (`_PULSE_EPOCH` 기준)
- ✅ `direction='bullish'/'bearish'` 올바른 컬럼명 사용
- ✅ `created_at >= today` 필터로 오늘 예측만 집계

**Placeholder 스캔:**
- 없음. 모든 코드 블록은 실제 구현체.

**Type 일관성:**
- `build_daily_pulse(db_path, today=None)` → Task 1 정의, Task 2에서 `lambda db: {"x":1}`로 mock → 일치
- `_PULSE_EPOCH` → Task 1 정의, test에서 `from data_collector.datalab import _PULSE_EPOCH` → 일치
- `dp-metric`, `dp-context`, `dp-headline`, `dp-date`, `dp-players-stat` → Task 3 HTML 정의, Task 4 JS에서 getElementById → 일치
- `dpShare()` → Task 4 정의, Task 3 HTML에서 `onclick="dpShare()"` → 일치
