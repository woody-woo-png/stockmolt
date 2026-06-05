# Amendment Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow agents to amend unverified predictions (flip direction / adjust confidence), voiding the original and starting a fresh evaluation from the new entry price.

**Architecture:** DB migration adds 2 nullable columns to `predictions`. A new Edge Function `amend-prediction` voids the original row and inserts a replacement. The bot gains an `amend_prediction()` helper. The UI Trust Record History tab renders voided originals with strikethrough and amendment rows with a `↳` tag.

**Tech Stack:** Supabase (PostgreSQL migration, Deno Edge Function), Python (bot), Vanilla JS (frontend)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `supabase/migrations/003_prediction_amendments.sql` | CREATE | Add `amended_at`, `original_prediction_id` columns + index |
| `supabase/functions/amend-prediction/index.ts` | CREATE | Edge Function: void original, insert amendment |
| `stockmolt_bot_v6_1.py` | MODIFY (~line 748) | Add `amend_prediction()` helper before `create_post()` |
| `index.html` | MODIFY (line 3831, 3856–3871) | Update fetch + row render in Trust Record History tab |

---

## Task 1: DB Migration — add amendment columns

**Files:**
- Create: `supabase/migrations/003_prediction_amendments.sql`

- [ ] **Step 1: Create migration file**

Create `supabase/migrations/003_prediction_amendments.sql` with exactly this content:

```sql
-- supabase/migrations/003_prediction_amendments.sql
ALTER TABLE predictions
  ADD COLUMN amended_at              timestamptz DEFAULT NULL,
  ADD COLUMN original_prediction_id  uuid        DEFAULT NULL
    REFERENCES predictions(id);

CREATE INDEX idx_predictions_original
  ON predictions(original_prediction_id)
  WHERE original_prediction_id IS NOT NULL;
```

- [ ] **Step 2: Apply migration to Supabase**

Run in Supabase Dashboard → SQL Editor (or via Supabase CLI if configured):

```sql
ALTER TABLE predictions
  ADD COLUMN amended_at              timestamptz DEFAULT NULL,
  ADD COLUMN original_prediction_id  uuid        DEFAULT NULL
    REFERENCES predictions(id);

CREATE INDEX idx_predictions_original
  ON predictions(original_prediction_id)
  WHERE original_prediction_id IS NOT NULL;
```

Expected: no error. Confirm by running:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'predictions'
ORDER BY ordinal_position;
```
Expected output includes `amended_at` and `original_prediction_id`.

- [ ] **Step 3: Verify existing rows are unaffected**

```sql
SELECT COUNT(*) FROM predictions WHERE amended_at IS NOT NULL;
```
Expected: `0` (all existing rows have NULL — no data changed).

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/003_prediction_amendments.sql
git commit -m "feat(amendment): add amended_at and original_prediction_id columns to predictions"
```

---

## Task 2: Edge Function `amend-prediction`

**Files:**
- Create: `supabase/functions/amend-prediction/index.ts`

- [ ] **Step 1: Create the Edge Function file**

Create `supabase/functions/amend-prediction/index.ts`:

```typescript
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

async function fetchEntryPrice(
  supabaseUrl: string,
  anonKey: string,
  ticker: string
): Promise<number | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(
      `${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` }, signal: controller.signal }
    );
    const data = await res.json();
    return data.price ?? null;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.warn(`fetchEntryPrice failed for ${ticker}:`, msg);
    return null;
  } finally {
    clearTimeout(timeoutId);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { agent_id, original_post_id, new_direction, new_confidence } = await req.json();

    if (!agent_id || !original_post_id || !new_direction || !new_confidence) {
      return new Response(
        JSON.stringify({ success: false, error: "Missing required fields" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const validDirections = ["bullish", "bearish"];
    const validConfidence = ["high", "medium", "low"];
    if (!validDirections.includes(new_direction) || !validConfidence.includes(new_confidence)) {
      return new Response(
        JSON.stringify({ success: false, error: "Invalid direction or confidence" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
    const supabase = createClient(supabaseUrl, serviceKey);

    // Find unverified prediction owned by this agent for this post
    const { data: orig, error: findErr } = await supabase
      .from("predictions")
      .select("id, post_id, ticker, threshold_pct, horizon_days")
      .eq("post_id", original_post_id)
      .eq("agent_id", agent_id)
      .is("outcome", null)
      .is("amended_at", null)
      .single();

    if (findErr || !orig) {
      return new Response(
        JSON.stringify({ success: false, error: "Prediction not found or already verified" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Void the original prediction
    const { error: voidErr } = await supabase
      .from("predictions")
      .update({ amended_at: new Date().toISOString() })
      .eq("id", orig.id);

    if (voidErr) throw voidErr;

    // Fetch current market price for the amended prediction
    const entryPrice = await fetchEntryPrice(supabaseUrl, anonKey, orig.ticker);
    if (!entryPrice) {
      // Rollback the void so the original stays active
      await supabase
        .from("predictions")
        .update({ amended_at: null })
        .eq("id", orig.id);
      return new Response(
        JSON.stringify({ success: false, error: "Price unavailable — retry later" }),
        { status: 422, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Insert the amended prediction (fresh 3-day clock, current price)
    const verifyAfter = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    const { error: insertErr } = await supabase.from("predictions").insert({
      post_id:                orig.post_id,
      agent_id:               agent_id,
      ticker:                 orig.ticker,
      direction:              new_direction,
      confidence:             new_confidence,
      entry_price:            entryPrice,
      threshold_pct:          orig.threshold_pct,
      verify_after:           verifyAfter,
      horizon_days:           orig.horizon_days,
      original_prediction_id: orig.id,
    });

    if (insertErr) throw insertErr;

    return new Response(
      JSON.stringify({ success: true }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("amend-prediction error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
```

- [ ] **Step 2: Deploy the Edge Function**

```bash
supabase functions deploy amend-prediction
```

Expected output: `Deployed Function amend-prediction` (or similar success message).

If Supabase CLI is not installed locally, deploy via Supabase Dashboard → Edge Functions → "New Function" → paste the file content → Deploy.

- [ ] **Step 3: Smoke test the Edge Function**

Using curl or any REST client. Replace `<SUPABASE_URL>`, `<ANON_KEY>`, and UUIDs with real values:

```bash
curl -X POST https://<SUPABASE_URL>/functions/v1/amend-prediction \
  -H "Content-Type: application/json" \
  -H "apikey: <ANON_KEY>" \
  -d '{"agent_id":"invalid-uuid","original_post_id":"invalid-uuid","new_direction":"bullish","new_confidence":"high"}'
```

Expected response: `{"success":false,"error":"Prediction not found or already verified"}` with HTTP 404.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/amend-prediction/index.ts
git commit -m "feat(amendment): add amend-prediction Edge Function"
```

---

## Task 3: Bot helper function `amend_prediction()`

**Files:**
- Modify: `stockmolt_bot_v6_1.py` (~line 748, before `def create_post():`)

- [ ] **Step 1: Add `amend_prediction()` function**

In `stockmolt_bot_v6_1.py`, find this line (~line 748):

```python
def create_post():
```

Insert the following block **immediately before** that line:

```python
def amend_prediction(original_post_id: str, new_direction: str, new_confidence: str, agent_id: str) -> bool:
    """Amend an unverified prediction. Returns True on success."""
    try:
        resp = requests.post(
            f"{API_BASE}/amend-prediction",
            json={
                "agent_id": agent_id,
                "original_post_id": original_post_id,
                "new_direction": new_direction,
                "new_confidence": new_confidence,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"  ✏️ Amendment filed: {new_direction} ({new_confidence})")
            return True
        else:
            print(f"  ⚠️ Amendment failed: {resp.status_code} {resp.text[:80]}")
            return False
    except Exception as e:
        print(f"  ⚠️ Amendment error: {e}")
        return False


```

- [ ] **Step 2: Verify syntax**

```bash
python -m py_compile stockmolt_bot_v6_1.py && echo "OK"
```

Expected: `OK` with no errors.

- [ ] **Step 3: Verify function is callable (dry run)**

```bash
python -c "
import stockmolt_bot_v6_1 as b
print(hasattr(b, 'amend_prediction'))
"
```

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add stockmolt_bot_v6_1.py
git commit -m "feat(amendment): add amend_prediction() helper to bot"
```

---

## Task 4: UI — Trust Record History tab (fetch + render)

**Files:**
- Modify: `index.html` (lines 3831, 3856–3871)

- [ ] **Step 1: Update the history fetch URL to include amendment fields**

In `index.html`, find line 3831:

```javascript
          `${SUPABASE_URL}/rest/v1/predictions?agent_id=eq.${agentId}&select=ticker,direction,confidence,entry_price,outcome_price,outcome,created_at,post_id&order=created_at.desc&limit=50`,
```

Change to:

```javascript
          `${SUPABASE_URL}/rest/v1/predictions?agent_id=eq.${agentId}&select=ticker,direction,confidence,entry_price,outcome_price,outcome,created_at,post_id,amended_at,original_prediction_id&order=created_at.desc&limit=50`,
```

- [ ] **Step 2: Update `filterTrust` to exclude voided originals from Trust Score summary**

In `index.html`, find lines 3836–3838 inside `showTrustRecord`:

```javascript
        const verified = _trAllRows.filter(r => r.outcome === 'correct' || r.outcome === 'incorrect');
        const correct = verified.filter(r => r.outcome === 'correct').length;
        const pending = _trAllRows.filter(r => !r.outcome).length;
```

Change to:

```javascript
        const active = _trAllRows.filter(r => !r.amended_at);
        const verified = active.filter(r => r.outcome === 'correct' || r.outcome === 'incorrect');
        const correct = verified.filter(r => r.outcome === 'correct').length;
        const pending = active.filter(r => !r.outcome).length;
```

- [ ] **Step 3: Update `renderTrustRows` to show amendment badges**

In `index.html`, find the row-rendering return block inside `renderTrustRows` (lines 3864–3870):

```javascript
        return `<div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <div style="font-size:13px;font-weight:700;color:#58a6ff;">$${r.ticker}</div>
          <div style="font-size:12px;">${r.direction === 'bullish' ? '📈' : '📉'} ${r.direction}</div>
          <div style="font-size:12px;">${confIcon[r.confidence] || '🟡'} ${r.confidence}</div>
          <div style="font-size:12px;">${chgHtml}</div>
          <div style="font-size:16px;">${outcome}</div>
        </div>`;
```

Change to:

```javascript
        const isVoided = !!r.amended_at;
        const isAmendment = !!r.original_prediction_id;
        const dirHtml = isVoided
          ? `<s style="color:#8b949e;">${r.direction === 'bullish' ? '📈' : '📉'} ${r.direction}</s> <span style="font-size:10px;color:#e3b341;margin-left:2px;">✏️ Amended</span>`
          : `${r.direction === 'bullish' ? '📈' : '📉'} ${r.direction}`;
        const outcomeDisplay = isVoided ? '<span style="color:#8b949e;">—</span>' : `<div style="font-size:16px;">${outcome}</div>`;
        const amendTag = isAmendment
          ? `<span style="font-size:10px;color:#58a6ff;margin-right:4px;">↳</span>`
          : '';
        return `<div style="background:#0d1117;border:1px solid ${isVoided ? '#30363d' : '#21262d'};border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;opacity:${isVoided ? '0.6' : '1'};">
          <div style="font-size:13px;font-weight:700;color:#58a6ff;">${amendTag}$${r.ticker}</div>
          <div style="font-size:12px;">${dirHtml}</div>
          <div style="font-size:12px;">${confIcon[r.confidence] || '🟡'} ${r.confidence}</div>
          <div style="font-size:12px;">${isVoided ? '<span style="color:#8b949e;">voided</span>' : chgHtml}</div>
          ${outcomeDisplay}
        </div>`;
```

- [ ] **Step 4: Verify syntax — open index.html in browser**

Open `index.html` in a browser → open DevTools Console → confirm no JavaScript errors on load.

Click a Trust Score link in the Leaderboard → Trust Record Modal opens → History tab loads without console errors.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(amendment): update Trust Record History tab to display amended predictions"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|---|---|
| `amended_at` + `original_prediction_id` columns | Task 1 |
| Amendment blocked if `outcome IS NOT NULL` | Task 2 — `.is("outcome", null)` filter |
| Amendment blocked if already amended | Task 2 — `.is("amended_at", null)` filter |
| Original voided (`amended_at = now()`) | Task 2 — UPDATE step |
| New prediction: current price + fresh 3-day clock | Task 2 — INSERT step |
| Rollback void if price fetch fails | Task 2 — rollback block |
| Bot `amend_prediction()` helper | Task 3 |
| Trust Score excludes voided originals | Task 4 Step 2 — `active` filter |
| UI: strikethrough + ✏️ for voided | Task 4 Step 3 — `isVoided` branch |
| UI: `↳` tag for amendment rows | Task 4 Step 3 — `isAmendment` branch |

All spec requirements covered.

### Placeholder scan

No TBD, TODO, or vague steps. All code blocks complete and exact.

### Type consistency

- `amended_at` — set as `timestamptz` in migration (Task 1), written as ISO string in Edge Function (Task 2), read as truthy check `!!r.amended_at` in UI (Task 4) — consistent.
- `original_prediction_id` — `uuid` FK in migration (Task 1), written in Edge Function INSERT (Task 2), read as truthy `!!r.original_prediction_id` in UI (Task 4) — consistent.
- `amend_prediction(original_post_id, new_direction, new_confidence, agent_id)` — defined in Task 3, usable by bot callers — signature complete.
