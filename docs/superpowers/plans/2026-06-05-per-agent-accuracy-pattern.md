# Per-Agent Accuracy Pattern Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a [History | Pattern] tab switcher to the Trust Record Modal, where the Pattern tab shows per-agent prediction accuracy broken down by sector, confidence, and weekly trend.

**Architecture:** Frontend-only change in `index.html`. The Pattern tab lazy-fetches verified predictions joined with `posts(sector)` via PostgREST. Three JS functions handle the tab switch, data load, and rendering. No DB schema changes.

**Tech Stack:** Vanilla JS, Supabase PostgREST REST API (`posts(sector)` join syntax)

---

## File Map

| File | Lines | Change |
|---|---|---|
| `index.html` | ~2453–2460 | Restructure modal: add tab buttons, wrap history content, add pattern pane |
| `index.html` | ~2555–2556 | Add `_trPatternLoaded`, `_trCurrentAgentId` state vars |
| `index.html` | ~3781 | Add `weekStart()` + `switchTrustTab()` before `showTrustRecord` |
| `index.html` | ~3845 | Add `renderPattern()` + `loadPatternData()` before `showPortfolio` |
| `index.html` | ~3781–3786 | Update `showTrustRecord()` — reset state + switch tab on open |

---

## Task 1: Restructure Trust Record Modal HTML

**Files:**
- Modify: `index.html` (~line 2453–2460)

- [ ] **Step 1: Replace the modal body below `#tr-summary`**

Find this exact block (~line 2453–2460):
```html
      <div id="tr-summary" style="font-size:12px;color:#8b949e;margin-bottom:16px;"></div>
      <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">
        <button onclick="filterTrust('all')" id="tr-f-all" style="background:#1f3a5f;border:1px solid #1f6feb;color:#58a6ff;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">All</button>
        <button onclick="filterTrust('correct')" id="tr-f-correct" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">✅ Correct</button>
        <button onclick="filterTrust('incorrect')" id="tr-f-incorrect" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">❌ Incorrect</button>
        <button onclick="filterTrust('pending')" id="tr-f-pending" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">⏳ Pending</button>
      </div>
      <div id="tr-rows" style="display:flex;flex-direction:column;gap:8px;"></div>
```

Replace with:
```html
      <div id="tr-summary" style="font-size:12px;color:#8b949e;margin-bottom:12px;"></div>
      <div style="display:flex;gap:6px;margin-bottom:14px;">
        <button id="tr-tab-history" onclick="switchTrustTab('history')" style="background:#1f3a5f;border:1px solid #1f6feb;color:#58a6ff;font-size:11px;padding:4px 12px;border-radius:4px;cursor:pointer;">📋 History</button>
        <button id="tr-tab-pattern" onclick="switchTrustTab('pattern')" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 12px;border-radius:4px;cursor:pointer;">📊 Pattern</button>
      </div>
      <div id="tr-history-pane" style="display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
          <button onclick="filterTrust('all')" id="tr-f-all" style="background:#1f3a5f;border:1px solid #1f6feb;color:#58a6ff;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">All</button>
          <button onclick="filterTrust('correct')" id="tr-f-correct" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">✅ Correct</button>
          <button onclick="filterTrust('incorrect')" id="tr-f-incorrect" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">❌ Incorrect</button>
          <button onclick="filterTrust('pending')" id="tr-f-pending" style="background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:11px;padding:4px 10px;border-radius:4px;cursor:pointer;">⏳ Pending</button>
        </div>
        <div id="tr-rows" style="display:flex;flex-direction:column;gap:8px;"></div>
      </div>
      <div id="tr-pattern-pane" style="display:none;">
        <div id="tr-pattern-content" style="color:#8b949e;text-align:center;padding:20px;">Loading pattern data...</div>
      </div>
```

- [ ] **Step 2: Verify HTML structure**

Open `index.html` in browser → Leaderboard tab → click any agent's Trust Score cell. Confirm:
- Modal opens with `[📋 History]` and `[📊 Pattern]` tab buttons visible
- History tab is active (blue) by default
- Prediction list loads normally under the tabs
- Pattern tab button is visible but not yet wired (clicking it shows nothing useful — that's expected at this step)

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(pattern): add History/Pattern tab buttons and panes to Trust Record Modal"
```

---

## Task 2: Add State Variables

**Files:**
- Modify: `index.html` (~line 2555)

- [ ] **Step 1: Add two state vars after `accuracySummaryPromise`**

Find (~line 2555):
```javascript
    let accuracySummaryCache = null;
    let accuracySummaryPromise = null;
```

Change to:
```javascript
    let accuracySummaryCache = null;
    let accuracySummaryPromise = null;
    let _trPatternLoaded = false;
    let _trCurrentAgentId = null;
```

- [ ] **Step 2: Verify vars exist**

Open `index.html` in browser → DevTools Console → type:
```javascript
console.log(_trPatternLoaded, _trCurrentAgentId)
```
Expected: `false null`

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(pattern): add _trPatternLoaded and _trCurrentAgentId state vars"
```

---

## Task 3: Add `weekStart()` and `switchTrustTab()` Functions

**Files:**
- Modify: `index.html` (~line 3781, just before `showTrustRecord`)

- [ ] **Step 1: Insert two functions before `showTrustRecord`**

Find this exact line (~line 3781):
```javascript
    async function showTrustRecord(agentId, agentName) {
```

Replace with:
```javascript
    function weekStart(dateStr) {
      const d = new Date(dateStr);
      d.setDate(d.getDate() - d.getDay());
      d.setHours(0, 0, 0, 0);
      return d.toISOString().split('T')[0];
    }

    function switchTrustTab(tab) {
      const isHistory = tab === 'history';
      const hp = document.getElementById('tr-history-pane');
      const pp = document.getElementById('tr-pattern-pane');
      hp.style.display = isHistory ? 'flex' : 'none';
      if (isHistory) hp.style.flexDirection = 'column';
      pp.style.display = isHistory ? 'none' : 'block';
      const hBtn = document.getElementById('tr-tab-history');
      const pBtn = document.getElementById('tr-tab-pattern');
      hBtn.style.background = isHistory ? '#1f3a5f' : '#161b22';
      hBtn.style.color = isHistory ? '#58a6ff' : '#8b949e';
      hBtn.style.borderColor = isHistory ? '#1f6feb' : '#30363d';
      pBtn.style.background = !isHistory ? '#1f3a5f' : '#161b22';
      pBtn.style.color = !isHistory ? '#58a6ff' : '#8b949e';
      pBtn.style.borderColor = !isHistory ? '#1f6feb' : '#30363d';
      if (!isHistory && !_trPatternLoaded) {
        loadPatternData(_trCurrentAgentId);
      }
    }

    async function showTrustRecord(agentId, agentName) {
```

- [ ] **Step 2: Verify tab switching works**

Open `index.html` in browser → Leaderboard → click any agent Trust Score. Confirm:
- `[📋 History]` is blue/active, `[📊 Pattern]` is grey
- Click `[📊 Pattern]`: Pattern tab turns blue, History tab turns grey, `#tr-history-pane` disappears, `#tr-pattern-pane` appears with "Loading pattern data..." text
- Click `[📋 History]`: switches back, prediction list is still visible
- DevTools Console should show no errors

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(pattern): add weekStart helper and switchTrustTab function"
```

---

## Task 4: Add `renderPattern()` and `loadPatternData()` Functions

**Files:**
- Modify: `index.html` (~line 3846, just before `showPortfolio`)

- [ ] **Step 1: Insert two functions before `showPortfolio`**

Find this exact line (~line 3846):
```javascript
    async function showPortfolio(btn) {
```

Replace with:
```javascript
    function renderPattern(sectorMap, confMap, weekMap) {
      const bar = pct => '█'.repeat(Math.round(pct / 10)) + '░'.repeat(10 - Math.round(pct / 10));
      const pctStr = (c, t) => t === 0 ? '—' : Math.round(c / t * 100) + '%';

      const sectors = Object.entries(sectorMap).sort((a, b) => b[1].t - a[1].t);
      const sectorHtml = sectors.length ? sectors.map(([s, v]) => {
        const p = v.t ? Math.round(v.c / v.t * 100) : 0;
        return `<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:6px;">
          <span style="width:72px;color:#e6edf3;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${s}</span>
          <span style="color:#3fb950;font-family:monospace;letter-spacing:-1px;">${bar(p)}</span>
          <span style="color:#8b949e;white-space:nowrap;">${pctStr(v.c, v.t)} (${v.c}/${v.t})</span>
        </div>`;
      }).join('') : '<div style="color:#8b949e;font-size:12px;">No sector data.</div>';

      const confRows = [['🔴','high','High'],['🟡','medium','Medium'],['🟢','low','Low']].map(([icon, key, label]) => {
        const v = confMap[key];
        const good = v.t > 0 && v.c / v.t >= 0.5;
        return `<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:6px;">
          <span style="width:82px;color:#e6edf3;">${icon} ${label}</span>
          <span style="width:54px;color:#8b949e;">${v.c}/${v.t}</span>
          <span style="color:${good ? '#3fb950' : '#f85149'};font-weight:700;">${pctStr(v.c, v.t)}</span>
        </div>`;
      }).join('');

      const weeks = Object.entries(weekMap).sort((a, b) => a[0].localeCompare(b[0])).slice(-4);
      const weekHtml = weeks.length ? weeks.map(([wk, v]) => {
        const p = v.t ? Math.round(v.c / v.t * 100) : 0;
        const label = new Date(wk + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        return `<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:6px;">
          <span style="width:52px;color:#8b949e;white-space:nowrap;">${label}</span>
          <span style="color:#3fb950;font-family:monospace;letter-spacing:-1px;">${bar(p)}</span>
          <span style="color:#8b949e;white-space:nowrap;">${pctStr(v.c, v.t)} (${v.c}/${v.t})</span>
        </div>`;
      }).join('') : '<div style="color:#8b949e;font-size:12px;">No weekly data yet.</div>';

      return `<div style="margin-bottom:16px;">
          <div style="font-size:11px;font-weight:700;color:#8b949e;margin-bottom:8px;letter-spacing:.08em;">📊 섹터별 정확도</div>
          ${sectorHtml}
        </div>
        <div style="margin-bottom:16px;">
          <div style="font-size:11px;font-weight:700;color:#8b949e;margin-bottom:8px;letter-spacing:.08em;">🎯 신뢰도별 성적</div>
          ${confRows}
        </div>
        <div>
          <div style="font-size:11px;font-weight:700;color:#8b949e;margin-bottom:8px;letter-spacing:.08em;">📈 최근 4주 추이</div>
          ${weekHtml}
        </div>`;
    }

    async function loadPatternData(agentId) {
      try {
        const res = await fetch(
          `${SUPABASE_URL}/rest/v1/predictions?select=confidence,outcome,created_at,posts(sector)` +
          `&agent_id=eq.${agentId}&outcome=not.is.null&outcome=neq.inconclusive&limit=1000`,
          { headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` } }
        );
        const json = await res.json();
        const rows = Array.isArray(json) ? json : [];
        if (!rows.length) {
          document.getElementById('tr-pattern-content').innerHTML =
            '<div style="text-align:center;color:#8b949e;padding:20px;">No verified predictions yet.</div>';
          _trPatternLoaded = true;
          return;
        }
        const sectorMap = {};
        const confMap = { high: { c: 0, t: 0 }, medium: { c: 0, t: 0 }, low: { c: 0, t: 0 } };
        const weekMap = {};
        rows.forEach(r => {
          const sector = r.posts?.sector || 'Other';
          const correct = r.outcome === 'correct' ? 1 : 0;
          if (!sectorMap[sector]) sectorMap[sector] = { c: 0, t: 0 };
          sectorMap[sector].t++;
          sectorMap[sector].c += correct;
          const conf = r.confidence in confMap ? r.confidence : 'medium';
          confMap[conf].t++;
          confMap[conf].c += correct;
          const wk = weekStart(r.created_at);
          if (!weekMap[wk]) weekMap[wk] = { c: 0, t: 0 };
          weekMap[wk].t++;
          weekMap[wk].c += correct;
        });
        document.getElementById('tr-pattern-content').innerHTML = renderPattern(sectorMap, confMap, weekMap);
        _trPatternLoaded = true;
      } catch(e) {
        document.getElementById('tr-pattern-content').innerHTML =
          '<div style="text-align:center;color:#f85149;padding:20px;">Failed to load pattern data.</div>';
      }
    }

    async function showPortfolio(btn) {
```

- [ ] **Step 2: Verify functions exist**

Open `index.html` in browser → DevTools Console → type:
```javascript
typeof renderPattern, typeof loadPatternData
```
Expected: `"function" "function"`

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(pattern): add renderPattern and loadPatternData functions"
```

---

## Task 5: Update `showTrustRecord()` to Reset State on Open

**Files:**
- Modify: `index.html` (~line 3799–3804, inside `showTrustRecord`)

- [ ] **Step 1: Add state reset and tab switch at the top of `showTrustRecord`**

Find this exact block (inside `showTrustRecord`, after the two new functions added in Task 3):
```javascript
    async function showTrustRecord(agentId, agentName) {
      const modal = document.getElementById('trust-modal');
      modal.style.display = 'flex';
      document.getElementById('tr-name').textContent = '🤖 ' + agentName;
      document.getElementById('tr-summary').textContent = 'Loading...';
      document.getElementById('tr-rows').innerHTML = '';
```

Replace with:
```javascript
    async function showTrustRecord(agentId, agentName) {
      _trPatternLoaded = false;
      _trCurrentAgentId = agentId;
      const modal = document.getElementById('trust-modal');
      modal.style.display = 'flex';
      switchTrustTab('history');
      document.getElementById('tr-name').textContent = '🤖 ' + agentName;
      document.getElementById('tr-summary').textContent = 'Loading...';
      document.getElementById('tr-rows').innerHTML = '';
      document.getElementById('tr-pattern-content').textContent = 'Loading pattern data...';
```

- [ ] **Step 2: Full end-to-end verify in browser**

Open `index.html` → Leaderboard tab. Pick any agent with a Trust Score. Click the Trust Score cell.

Check History tab (default):
- Modal opens on `[📋 History]` tab (blue)
- Summary line shows: `Trust: X% · N verified · M pending`
- Prediction list loads with rows

Check Pattern tab:
- Click `[📊 Pattern]` — tab turns blue, history pane hides
- `#tr-pattern-content` shows "Loading pattern data..." briefly then renders:
  - `📊 섹터별 정확도` — progress bars per sector (sorted by total predictions)
  - `🎯 신뢰도별 성적` — 3 rows: 🔴 High / 🟡 Medium / 🟢 Low with accuracy%
  - `📈 최근 4주 추이` — up to 4 weeks with bars
- If agent has no verified predictions: "No verified predictions yet."

Check re-open behavior:
- Close modal (`✕`), open a **different** agent's Trust Record
- Pattern tab should load fresh data for the new agent (not cache the previous one)

Check DevTools Console: no errors.

- [ ] **Step 3: Grep for stale references**

Run in terminal:
```powershell
Select-String -Path "index.html" -Pattern "tr-history-pane|tr-pattern-pane|tr-tab-history|tr-tab-pattern|switchTrustTab|loadPatternData|renderPattern|_trPatternLoaded|_trCurrentAgentId|weekStart"
```
Expected: all 9 identifiers appear. None should appear only once (every identifier should have both declaration and usage).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(pattern): wire showTrustRecord to reset pattern state and switch to History tab on open"
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task |
|---|---|
| `[History] [Pattern]` tab switcher in modal | Task 1 + Task 3 |
| History pane: filter buttons + prediction rows (unchanged behavior) | Task 1 |
| Pattern pane: hidden by default, lazy-load on first open | Task 1 + Task 3 (`switchTrustTab`) |
| PostgREST JOIN `posts(sector)` to get real sector | Task 4 (`loadPatternData` fetch URL) |
| 섹터별 정확도 — bars per sector, sorted by total | Task 4 (`renderPattern`) |
| 신뢰도별 성적 — High / Medium / Low rows with accuracy% | Task 4 (`renderPattern`) |
| 최근 4주 추이 — last 4 calendar weeks with data | Task 4 (`renderPattern`, `weekStart`) |
| No verified predictions → empty state message | Task 4 (`loadPatternData`) |
| Fetch error → error message (not broken UI) | Task 4 (`loadPatternData` catch) |
| Null sector falls back to "Other" | Task 4 (`r.posts?.sector \|\| 'Other'`) |
| inconclusive excluded | Task 4 (query param `outcome=neq.inconclusive`) |
| Re-opening modal resets Pattern tab (loads fresh for new agent) | Task 5 |

All spec requirements covered.

### Placeholder scan

No TBD, TODO, or vague steps. All code blocks are complete and exact.

### Type consistency

- `_trPatternLoaded` (bool): declared Task 2, read in `switchTrustTab` Task 3, set in Task 4 — consistent
- `_trCurrentAgentId` (string|null): declared Task 2, set in Task 5, read in `switchTrustTab` Task 3 → passed to `loadPatternData` Task 4 — consistent
- `renderPattern(sectorMap, confMap, weekMap)`: defined Task 4, called in Task 4 with same 3 args — consistent
- `weekStart(dateStr)`: defined Task 3, called in Task 4 — consistent
- `tr-history-pane`, `tr-pattern-pane`, `tr-tab-history`, `tr-tab-pattern`, `tr-pattern-content`: declared Task 1 HTML, referenced in Task 3 JS — consistent
