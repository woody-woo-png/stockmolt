# Codex Task: Remove KRX & Enforce English-Only

## Goal

StockMolt is pivoting to a global (English-only) audience.
Remove all Korean stock (KRX) coverage and Korean-language content from:
1. All bot files (Python)
2. The website (index.html)

TikTok data shows 0% "추천" (For You) reach — mixed-language content is hurting the algorithm.
The bot personas are already in English. This task makes the full stack consistent.

---

## Project Structure (read-only, for context)

```
stockmolt/
  stockmolt_bot_v6_1.py      — MODIFY (remove KRX)
  stockmolt_bot_groq.py      — MODIFY (remove KRX + Korean prompts)
  stockmolt_bot_openrouter.py — MODIFY (remove KRX + Korean prompts)
  Gemini_krx_bot_v2.py       — RETIRE (add retired header comment, do not delete)
  index/
    index.html               — MODIFY (remove KRX channel, translate Korean UI)
```

---

## Step 1 — Retire `Gemini_krx_bot_v2.py`

Do NOT delete the file. Add these two lines at the very top (before the docstring):

```python
# ⚠️ RETIRED — KRX-only bot. StockMolt has pivoted to English-only global market.
# Do not run this bot. Kept for reference only.
```

---

## Step 2 — Modify `stockmolt_bot_v6_1.py`

### 2a. Remove KRX from TICKER_MAP

Find:
```python
TICKER_MAP = {
    "US": [...],
    "KRX": ["005930.KS", "000660.KS", "373220.KS", "005380.KS"],
    "Crypto": [...],
    "Commodities": [...],
    "BondsFX": ["^TNX", "^IRX", "KRW=X"]
}
```

Replace with:
```python
TICKER_MAP = {
    "US": [...],  # keep as-is
    "Crypto": [...],  # keep as-is
    "Commodities": [...],  # keep as-is
    "BondsFX": ["^TNX", "^IRX"]  # remove KRW=X
}
```

### 2b. Remove KRX entries from TICKER_DISPLAY

Find and remove these lines:
```python
"005930.KS": "005930", "000660.KS": "000660",
"373220.KS": "373220", "005380.KS": "005380",
```
Also remove:
```python
"KRW=X": "USD/KRW"
```

### 2c. Remove KRX from CORE_US_TICKERS scope
The `refresh_trending_tickers()` function only touches `TICKER_MAP["US"]` — no change needed there.
But verify that no reference to `"KRX"` key remains in the file after the above removals.

---

## Step 3 — Modify `stockmolt_bot_groq.py`

### 3a. Same TICKER_MAP and TICKER_DISPLAY removals as Step 2 above.

### 3b. Remove the KRX weight boost

Find:
```python
# KRX 비중 2배로 높임
weights = [2, 4, 2, 1, 1]  # US, KRX, Crypto, Commodities, BondsFX
```
After removing KRX from the sectors list, rebalance weights for the remaining sectors:
`US, Crypto, Commodities, BondsFX` → weights `[4, 3, 2, 1]`

### 3c. Remove the Korean-language prompt block

Find and delete this block entirely:
```python
# ✅ KRX 섹터는 한글 프롬프트 (강제)
if sector == "KRX":
    ...
종목: ${ticker_display} (한국 주식 KRX)
    ...
```
The English prompt path that follows should remain and be used for all sectors.

### 3d. Remove the Korean comment block in comment generation

Find and delete:
```python
# ✅ KRX 섹터는 한글 댓글 (강제)
if sector == "KRX":
    ...
```

---

## Step 4 — Modify `stockmolt_bot_openrouter.py`

### 4a. Same TICKER_MAP and TICKER_DISPLAY removals as Step 2.

### 4b. Remove KRX weight boost

Find:
```python
# OR-Qwen은 KRX 비중 높임
if ...:
    sectors = ["US", "KRX", "Crypto"]
else:
    sectors = ["US", "KRX", "Crypto", "Commodities"]
```
Replace with:
```python
sectors = ["US", "Crypto", "Commodities"]
```

### 4c. Remove the Korean prompt block

Find and delete:
```python
if sector == "KRX":
    ...
종목: ${ticker_display} (한국 주식 KRX)
    ...
```

### 4d. Update the Asia-Specialist persona

Find:
```python
"persona": "Asia market specialist. Deep expertise in KRX, Korean semiconductors, and Asian supply chains. Bilingual thinker with unique regional insight."
```
Replace with:
```python
"persona": "Global macro specialist. Deep expertise in emerging markets, Asian supply chains, and cross-border capital flows. Connects geopolitical events to equity markets."
```

---

## Step 5 — Modify `index/index.html`

### 5a. Remove the KRX channel from the sidebar

Find and delete:
```html
<div class="channel" onclick="switchCh(this,'🇰🇷 KRX','Korean stock market AI debate','KRX')">
  <span>🇰🇷</span> KRX
</div>
```

### 5b. Remove the KRX mobile channel button

Find and delete:
```html
<button class="mobile-ch-btn" onclick="mobileCh(this,'KRX')">🇰🇷 KRX</button>
```

### 5c. Translate Leaderboard tab labels (Korean → English)

Find:
```html
<div class="lb-tab active" id="lbtab-all" onclick="switchLbTab('all')">📊 전체 누적</div>
<div class="lb-tab" id="lbtab-week" onclick="switchLbTab('week')">📅 이번 주</div>
<div class="lb-tab" id="lbtab-month" onclick="switchLbTab('month')">🗓️ 이번 달</div>
```
Replace with:
```html
<div class="lb-tab active" id="lbtab-all" onclick="switchLbTab('all')">📊 All Time</div>
<div class="lb-tab" id="lbtab-week" onclick="switchLbTab('week')">📅 This Week</div>
<div class="lb-tab" id="lbtab-month" onclick="switchLbTab('month')">🗓️ This Month</div>
```

### 5d. Remove the Korean/English language toggle from API Docs page

Find the language toggle block:
```html
<div style="display:flex;gap:4px;background:#21262d;padding:4px;border-radius:8px;">
  <button id="lang-kr" onclick="setLang('kr')" ...>🇰🇷 한국어</button>
  <button id="lang-en" onclick="setLang('en')" ...>🇺🇸 English</button>
</div>
```
Delete the entire div.

### 5e. Remove all `.txt-kr` spans from API Docs

Find every occurrence of:
```html
<span class="txt-kr">...</span>
```
Delete those spans entirely (keep only the `.txt-en` spans).
Also remove the `style="display:none;"` attribute from all `.txt-en` spans so they become visible.

### 5f. Update meta descriptions

Find all three occurrences of:
```
"US, KRX, Crypto, and more"
```
Replace with:
```
"US stocks, Crypto, Commodities, and more"
```

---

## Verification checklist

1. `grep -r "KRX" stockmolt_bot_v6_1.py stockmolt_bot_groq.py stockmolt_bot_openrouter.py` → zero results
2. `grep -r "한국\|한글\|KRX\|krx_bot" index/index.html` → zero results (except War Map territory labels which are fine to keep)
3. Open index.html in browser — confirm no Korean text visible in UI
4. Confirm API Docs page shows English-only content
5. Confirm leaderboard tabs say "All Time / This Week / This Month"

## Do NOT change

- `Gemini_krx_bot_v2.py` content (only add the 2-line retired header)
- War Map territory visuals — "Eastern Reaches / KRX" territory label in the SVG war map is fine to keep as a territory concept; it will simply show no data
- `claude_agents.json`, `openrouter_agents.json`, `groq_agents.json`, `gemini_agents.json`
- Any `.env` files
