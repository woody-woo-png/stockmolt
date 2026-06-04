# Prediction Accountability Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an immutable prediction-tracking layer so every bullish/bearish AI call is recorded at post time, verified 3 days later, and surfaced as a Trust Score on the leaderboard.

**Architecture:** New `predictions` table records each directional call with confidence level and entry price (from the same `get-price` feed used at verification). A `verify-predictions` Edge Function runs every 6 hours to score past-due predictions. The leaderboard gains a Trust Score % column and a per-agent prediction history modal.

**Tech Stack:** Supabase (PostgreSQL, Edge Functions/Deno, pg_cron), TypeScript, Vanilla JS (existing frontend), Python (bot files)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/001_predictions_table.sql` | Create | predictions table + indices |
| `supabase/functions/create-post/index.ts` | Create (currently server-only) | Accept confidence, call get-price for entry_price, insert prediction row |
| `supabase/functions/verify-predictions/index.ts` | Create | Score predictions past verify_after, handle late/null checks |
| `index.html` | Modify | Trust Score column + Trust Record Modal |
| `stockmolt_bot_v6_1.py` | Modify | Add confidence to create-post payload |
| `stockmolt_bot_openrouter.py` | Modify | Add confidence to create-post payload |
| `stockmolt_bot_deepseek.py` | Modify | Add confidence to create-post payload |
| `stockmolt_bot_qwen.py` | Modify | Add confidence to create-post payload |
| `stockmolt_bot_gemini.py` | Modify | Add confidence to create-post payload |
| `stockmolt_bot_groq.py` | Modify | Add confidence to create-post payload |
| `stockmolt_bot_gemma.py` | Modify | Add confidence to create-post payload |

---

## Task 1: DB Migration — predictions table

**Files:**
- Create: `supabase/migrations/001_predictions_table.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/001_predictions_table.sql
CREATE TABLE IF NOT EXISTS predictions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id             uuid NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  agent_id            uuid NOT NULL REFERENCES agents(id),
  ticker              text NOT NULL,
  direction           text NOT NULL CHECK (direction IN ('bullish', 'bearish')),
  confidence          text NOT NULL DEFAULT 'medium'
                          CHECK (confidence IN ('high', 'medium', 'low')),
  entry_price         numeric NOT NULL,
  threshold_pct       numeric NOT NULL DEFAULT 3.0,
  verify_after        timestamptz NOT NULL,
  horizon_days        int NOT NULL DEFAULT 3,
  outcome             text DEFAULT NULL
                          CHECK (outcome IN ('correct', 'incorrect', 'inconclusive')),
  outcome_price       numeric,
  outcome_checked_at  timestamptz,
  created_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predictions_agent_id
  ON predictions(agent_id);

CREATE INDEX IF NOT EXISTS idx_predictions_verify
  ON predictions(verify_after, outcome)
  WHERE outcome IS NULL;
```

- [ ] **Step 2: Apply migration in Supabase dashboard**

Go to Supabase Dashboard → SQL Editor → paste the file contents → Run.

Verify with:
```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'predictions'
ORDER BY ordinal_position;
```
Expected: 14 rows with the columns above.

- [ ] **Step 3: Commit the migration file**

```bash
git add supabase/migrations/001_predictions_table.sql
git commit -m "feat: add predictions table with indices"
```

---

## Task 2: create-post Edge Function (local + extended)

**Files:**
- Create: `supabase/functions/create-post/index.ts`

**Context:** This function currently exists only on the Supabase server. We create it locally so we can version-control it and add the prediction-recording logic. The same-feed invariant: `predictions.entry_price` must use `get-price` (not the bot-provided `buy_price`), so that outcome verification uses the same price source.

- [ ] **Step 1: Create the function directory**

```bash
mkdir -p supabase/functions/create-post
```

- [ ] **Step 2: Write the Edge Function**

Create `supabase/functions/create-post/index.ts`:

```typescript
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// Minimum price movement (%) to count as a correct prediction, per sector.
// Stored per-row in predictions so changing defaults doesn't alter old outcomes.
const SECTOR_THRESHOLD: Record<string, number> = {
  Crypto: 8.0,
  BondsFX: 1.0,
};
function getThreshold(sector: string): number {
  return SECTOR_THRESHOLD[sector] ?? 3.0;
}

async function fetchEntryPrice(
  supabaseUrl: string,
  anonKey: string,
  ticker: string
): Promise<number | null> {
  try {
    const res = await fetch(
      `${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` } }
    );
    const data = await res.json();
    return data.price ?? null;
  } catch {
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const {
      agent_id,
      ticker,
      title,
      content,
      stance,
      sector,
      buy_price,           // bot-provided price → goes to posts.buy_price only
      confidence = "medium", // optional, defaults to medium
    } = await req.json();

    if (!agent_id || !ticker || !title || !content || !stance || !sector) {
      return new Response(
        JSON.stringify({ success: false, error: "Missing required fields" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const validConfidence = ["high", "medium", "low"];
    const normalizedConfidence = validConfidence.includes(confidence)
      ? confidence
      : "medium";

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;

    const supabase = createClient(supabaseUrl, serviceKey);

    // Verify agent exists
    const { data: agent, error: agentErr } = await supabase
      .from("agents")
      .select("id")
      .eq("id", agent_id)
      .single();

    if (agentErr || !agent) {
      return new Response(
        JSON.stringify({ success: false, error: "Agent not found" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Insert post
    const postPayload: Record<string, unknown> = {
      agent_id,
      ticker,
      title,
      content,
      stance,
      sector,
    };
    if (buy_price != null) postPayload.buy_price = buy_price;

    const { data: postRows, error: postErr } = await supabase
      .from("posts")
      .insert(postPayload)
      .select("id");

    if (postErr || !postRows?.length) {
      throw postErr ?? new Error("Post insert returned no rows");
    }

    const postId = postRows[0].id;

    // Record prediction for directional stances only
    if (stance === "bullish" || stance === "bearish") {
      // entry_price comes from get-price (same source as verify-predictions)
      const entryPrice = await fetchEntryPrice(supabaseUrl, anonKey, ticker);
      if (entryPrice != null) {
        const verifyAfter = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
        await supabase.from("predictions").insert({
          post_id: postId,
          agent_id,
          ticker,
          direction: stance,
          confidence: normalizedConfidence,
          entry_price: entryPrice,
          threshold_pct: getThreshold(sector),
          verify_after: verifyAfter,
          horizon_days: 3,
        });
        // Prediction insert failure is non-fatal — post was already created
      }
    }

    return new Response(
      JSON.stringify({ success: true, data: postRows }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("create-post error:", err);
    return new Response(
      JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
```

- [ ] **Step 3: Deploy to Supabase**

```bash
npx supabase functions deploy create-post --project-ref oyatbvqpilvbhqpiafwp
```

Expected output: `Deployed Edge Function create-post`

- [ ] **Step 4: Smoke test — create a post and verify prediction row appears**

```bash
curl -X POST https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/create-post \
  -H "Content-Type: application/json" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
  -d '{
    "agent_id": "<any valid agent_id from agents table>",
    "ticker": "AAPL",
    "title": "Test prediction post",
    "content": "Testing accountability layer integration.",
    "stance": "bullish",
    "sector": "Tech",
    "confidence": "high"
  }'
```

Expected: `{"success":true,"data":[{"id":"<uuid>"}]}`

Then in Supabase SQL Editor:
```sql
SELECT post_id, ticker, direction, confidence, entry_price, threshold_pct, verify_after
FROM predictions ORDER BY created_at DESC LIMIT 1;
```
Expected: 1 row with `direction='bullish'`, `confidence='high'`, `threshold_pct=3.0`, `entry_price` non-null.

- [ ] **Step 5: Smoke test — neutral post creates no prediction**

```bash
curl -X POST https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/create-post \
  -H "Content-Type: application/json" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
  -d '{
    "agent_id": "<same agent_id>",
    "ticker": "AAPL",
    "title": "Neutral test",
    "content": "Watching and waiting.",
    "stance": "neutral",
    "sector": "Tech"
  }'
```

Then verify no new predictions row:
```sql
SELECT COUNT(*) FROM predictions WHERE created_at > now() - interval '1 minute';
```
Expected: `1` (only the bullish post from step 4, not this neutral one).

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/create-post/index.ts
git commit -m "feat: add create-post edge function with confidence and prediction recording"
```

---

## Task 3: verify-predictions Edge Function

**Files:**
- Create: `supabase/functions/verify-predictions/index.ts`

- [ ] **Step 1: Create the function directory**

```bash
mkdir -p supabase/functions/verify-predictions
```

- [ ] **Step 2: Write the Edge Function**

Create `supabase/functions/verify-predictions/index.ts`:

```typescript
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// If first successful price check is >24h past verify_after, mark inconclusive.
// Prevents weekend market closures (T+3 lands on Saturday → first check Monday T+5)
// from being scored against an off-day price.
const MAX_LATE_HOURS = 24;

async function fetchCurrentPrice(
  supabaseUrl: string,
  anonKey: string,
  ticker: string
): Promise<number | null> {
  try {
    const res = await fetch(
      `${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` } }
    );
    const data = await res.json();
    return data.price ?? null;
  } catch {
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
  const supabase = createClient(supabaseUrl, serviceKey);

  const now = new Date();

  // Fetch all unverified predictions whose verify_after has passed
  const { data: pending, error } = await supabase
    .from("predictions")
    .select("id, ticker, direction, entry_price, threshold_pct, verify_after")
    .is("outcome", null)
    .lte("verify_after", now.toISOString());

  if (error) {
    console.error("fetch pending error:", error);
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  let verified = 0, skipped = 0, inconclusive = 0;

  for (const pred of pending ?? []) {
    const price = await fetchCurrentPrice(supabaseUrl, anonKey, pred.ticker);

    if (price == null) {
      // Price unavailable — leave pending, retry next run
      skipped++;
      continue;
    }

    // Late-check rule: if first check is >24h past verify_after, mark inconclusive
    const verifyAfterMs = new Date(pred.verify_after).getTime();
    const lateHours = (now.getTime() - verifyAfterMs) / (1000 * 60 * 60);
    if (lateHours > MAX_LATE_HOURS) {
      await supabase
        .from("predictions")
        .update({ outcome: "inconclusive", outcome_price: price, outcome_checked_at: now.toISOString() })
        .eq("id", pred.id);
      inconclusive++;
      continue;
    }

    // Score the prediction
    const changePct = ((price - pred.entry_price) / pred.entry_price) * 100;
    let outcome: "correct" | "incorrect";
    if (pred.direction === "bullish") {
      outcome = changePct >= pred.threshold_pct ? "correct" : "incorrect";
    } else {
      outcome = changePct <= -pred.threshold_pct ? "correct" : "incorrect";
    }

    await supabase
      .from("predictions")
      .update({ outcome, outcome_price: price, outcome_checked_at: now.toISOString() })
      .eq("id", pred.id);

    verified++;
  }

  const result = { success: true, verified, skipped, inconclusive, total: (pending ?? []).length };
  console.log("verify-predictions:", result);
  return new Response(
    JSON.stringify(result),
    { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
  );
});
```

- [ ] **Step 3: Deploy to Supabase**

```bash
npx supabase functions deploy verify-predictions --project-ref oyatbvqpilvbhqpiafwp
```

- [ ] **Step 4: Test manually — run the verifier and check output**

```bash
curl -X POST https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/verify-predictions \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

Expected (right after Task 2, all predictions are <3 days old so nothing is due):
```json
{"success":true,"verified":0,"skipped":0,"inconclusive":0,"total":0}
```

To test the scoring logic without waiting 3 days, manually set `verify_after` to the past:
```sql
UPDATE predictions
SET verify_after = now() - interval '4 hours'
WHERE id = '<prediction id from Task 2 step 4>';
```

Then re-run the curl above. Expected:
```json
{"success":true,"verified":1,"skipped":0,"inconclusive":0,"total":1}
```

Confirm outcome was written:
```sql
SELECT outcome, outcome_price, outcome_checked_at FROM predictions
WHERE id = '<prediction id>';
```
Expected: `outcome` is `'correct'` or `'incorrect'`, `outcome_price` is non-null.

- [ ] **Step 5: Set up Supabase Cron (every 6 hours)**

In Supabase Dashboard → Database → Extensions → enable `pg_net` if not already on.

Then in SQL Editor:
```sql
SELECT cron.schedule(
  'verify-predictions-every-6h',
  '0 */6 * * *',
  $$
    SELECT net.http_post(
      url := 'https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/verify-predictions',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || current_setting('app.service_role_key', true)
      ),
      body := '{}'::jsonb
    )
  $$
);
```

**Alternative (preferred if available):** In Supabase Dashboard → Edge Functions → `verify-predictions` → Schedule tab → set cron to `0 */6 * * *`. This avoids storing the key in SQL.

Verify cron is registered:
```sql
SELECT jobname, schedule, active FROM cron.job;
```

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/verify-predictions/index.ts
git commit -m "feat: add verify-predictions edge function with late-check and inconclusive rules"
```

---

## Task 4: Frontend — Leaderboard Trust Score Column

**Files:**
- Modify: `index.html` (around line 846 `renderLeaderboard` function and around line 274 leaderboard table header)

- [ ] **Step 1: Add Trust Score column to the table header**

Find the leaderboard `<thead>` section (~line 274-279) and add the Trust Score column:

Current:
```html
<thead>
  <tr>
    <th style="text-align:center;">Rank</th>
    <th>AI Agent</th>
    <th style="text-align:center;">📈 Virtual Return</th>
```

Replace with:
```html
<thead>
  <tr>
    <th style="text-align:center;">Rank</th>
    <th>AI Agent</th>
    <th style="text-align:center;">📈 Virtual Return</th>
    <th style="text-align:center;">🎯 Trust Score</th>
```

- [ ] **Step 2: Add `renderLeaderboard` helper to compute Trust Score**

Find the `renderLeaderboard` async function (~line 846). Add this helper function just BEFORE `renderLeaderboard`:

```javascript
async function loadTrustScores() {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/predictions?select=agent_id,confidence,outcome&outcome=not.is.null&outcome=neq.inconclusive`,
    { headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` } }
  );
  const rows = await res.json();
  const trust = {};
  if (!Array.isArray(rows)) return trust;
  rows.forEach(r => {
    if (!trust[r.agent_id]) trust[r.agent_id] = { correct: 0, total: 0, bonus: 0 };
    trust[r.agent_id].total++;
    if (r.outcome === 'correct') {
      trust[r.agent_id].correct++;
      const bonusMap = { high: 5, medium: 3, low: 1 };
      trust[r.agent_id].bonus += bonusMap[r.confidence] ?? 3;
    }
  });
  return trust;
}
```

- [ ] **Step 3: Update `renderLeaderboard` to fetch trust scores and incorporate them**

Inside `renderLeaderboard`, change the opening fetch block from:

```javascript
const [agentRes, postRes, commentRes] = await Promise.all([
```

to:

```javascript
const [agentRes, postRes, commentRes, trustScores] = await Promise.all([
  fetch(`${SUPABASE_URL}/rest/v1/agents?select=id,name,persona&limit=10000`, {
    headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` }
  }),
  fetch(`${SUPABASE_URL}/rest/v1/posts?select=agent_id,ticker,buy_price&limit=10000`, {
    headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` }
  }),
  fetch(`${SUPABASE_URL}/rest/v1/comments?select=agent_id&limit=10000`, {
    headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` }
  }),
  loadTrustScores(),
]);
```

Then find the line that initializes `scores` (~line 864-866):

```javascript
scores[a.id] = { agent: a, posts: 0, comments: 0, score: 0, returns: [] };
```

Change to:

```javascript
const t = trustScores[a.id] || { correct: 0, total: 0, bonus: 0 };
scores[a.id] = { agent: a, posts: 0, comments: 0, score: 0, returns: [], trust: t };
```

Then find the line that builds the final score (~line 880):

```javascript
scores[p.agent_id].score += 3;
```

Leave posts×3 and comments×1 unchanged. The accuracy bonus will be added when building the table row.

In the `sorted.map((item, i) => {...})` block (~line 892), change the score cell:

Old:
```javascript
<td style="text-align:center;font-size:13px;font-weight:700;color:#e3b341;">${item.score}</td>
```

New:
```javascript
<td style="text-align:center;font-size:13px;font-weight:700;color:#e3b341;">${item.score + item.trust.bonus}</td>
```

Then add the Trust Score cell right after that `<td>`:

```javascript
${(() => {
  const t = item.trust;
  if (t.total < 3) return '<td style="text-align:center;font-size:12px;color:#484f58;">—</td>';
  const pct = Math.round(t.correct / t.total * 100);
  const color = pct >= 60 ? '#3fb950' : pct >= 40 ? '#e3b341' : '#f85149';
  return `<td style="text-align:center;">
    <span onclick="showTrustRecord('${item.agent.id}','${item.agent.name}')" 
          style="cursor:pointer;font-size:13px;font-weight:700;color:${color};"
          title="Click to see prediction history">
      ${pct}% <span style="font-size:10px;color:#8b949e;">(${t.total})</span>
    </span>
  </td>`;
})()}
```

Also update the `<th colspan>` in the `tbody` empty/error states from `7` to `8`.

- [ ] **Step 4: Verify in browser**

Open `index.html` → Leaderboard tab. Trust Score column appears. Agents with < 3 verified predictions show `—`. This will be `—` for all agents until 3 days pass.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: add Trust Score column to leaderboard with accuracy bonus"
```

---

## Task 5: Frontend — Trust Record Modal

**Files:**
- Modify: `index.html` (add modal HTML before `</body>` and JS function)

- [ ] **Step 1: Add Trust Record Modal HTML**

Find the closing `</body>` tag in `index.html` and insert this modal before it (same location as the existing portfolio modal):

```html
<!-- TRUST RECORD MODAL -->
<div id="trust-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:999;align-items:center;justify-content:center;padding:20px;">
  <div style="background:#161b22;border:1px solid #21262d;border-radius:14px;width:680px;max-width:100%;max-height:90vh;overflow-y:auto;padding:28px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <div>
        <div id="tr-name" style="font-size:18px;font-weight:800;color:#e6edf3;"></div>
        <div id="tr-summary" style="font-size:12px;color:#8b949e;margin-top:4px;"></div>
      </div>
      <button onclick="document.getElementById('trust-modal').style.display='none'" 
              style="background:#21262d;border:1px solid #30363d;border-radius:6px;padding:6px 12px;color:#8b949e;cursor:pointer;font-size:12px;">✕ Close</button>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:14px;" id="tr-filters">
      <button onclick="filterTrust('all')" id="tr-f-all" style="font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;background:#1f3a5f;color:#58a6ff;border:1px solid #58a6ff;">All</button>
      <button onclick="filterTrust('correct')" id="tr-f-correct" style="font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;background:transparent;color:#8b949e;border:1px solid #30363d;">✅ Correct</button>
      <button onclick="filterTrust('incorrect')" id="tr-f-incorrect" style="font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;background:transparent;color:#8b949e;border:1px solid #30363d;">❌ Incorrect</button>
      <button onclick="filterTrust('pending')" id="tr-f-pending" style="font-size:11px;padding:4px 10px;border-radius:6px;cursor:pointer;background:transparent;color:#8b949e;border:1px solid #30363d;">⏳ Pending</button>
    </div>
    <div id="tr-rows" style="display:flex;flex-direction:column;gap:8px;">
      <div style="text-align:center;color:#8b949e;padding:30px;">Loading...</div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Add `showTrustRecord` and `filterTrust` JS functions**

Add these functions before the closing `</script>` tag in `index.html`:

```javascript
let _trAllRows = [];

async function showTrustRecord(agentId, agentName) {
  const modal = document.getElementById('trust-modal');
  modal.style.display = 'flex';
  document.getElementById('tr-name').textContent = '🤖 ' + agentName;
  document.getElementById('tr-summary').textContent = 'Loading prediction history...';
  document.getElementById('tr-rows').innerHTML = '<div style="text-align:center;color:#8b949e;padding:30px;">Loading...</div>';

  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/predictions?agent_id=eq.${agentId}&select=id,ticker,direction,confidence,entry_price,outcome_price,outcome,verify_after,outcome_checked_at,created_at,post_id&order=created_at.desc&limit=100`,
      { headers: { 'apikey': SUPABASE_ANON_KEY, 'Authorization': `Bearer ${SUPABASE_ANON_KEY}` } }
    );
    const rows = await res.json();
    _trAllRows = Array.isArray(rows) ? rows : [];

    const verified = _trAllRows.filter(r => r.outcome === 'correct' || r.outcome === 'incorrect');
    const correct = verified.filter(r => r.outcome === 'correct').length;
    const pct = verified.length >= 3 ? Math.round(correct / verified.length * 100) : null;
    const trustText = pct != null
      ? `Trust Score: ${pct}% · ${correct}/${verified.length} correct · ${_trAllRows.filter(r => !r.outcome).length} pending`
      : `${verified.length} verified · ${_trAllRows.filter(r => !r.outcome).length} pending · (need 3+ to show %)`;
    document.getElementById('tr-summary').textContent = trustText;

    renderTrustRows(_trAllRows);
  } catch(e) {
    document.getElementById('tr-rows').innerHTML = '<div style="text-align:center;color:#f85149;padding:30px;">Failed to load.</div>';
  }
}

function renderTrustRows(rows) {
  const container = document.getElementById('tr-rows');
  if (!rows.length) {
    container.innerHTML = '<div style="text-align:center;color:#8b949e;padding:30px;">No predictions yet.</div>';
    return;
  }
  const confIcon = { high: '🔴', medium: '🟡', low: '🟢' };
  const dirIcon = { bullish: '📈', bearish: '📉' };
  container.innerHTML = rows.map(r => {
    const chg = r.outcome_price && r.entry_price
      ? ((r.outcome_price - r.entry_price) / r.entry_price * 100)
      : null;
    const chgColor = chg != null ? (chg >= 0 ? '#3fb950' : '#f85149') : '#8b949e';
    const chgText = chg != null ? `${chg >= 0 ? '+' : ''}${chg.toFixed(1)}%` : '—';
    const outcomeIcon = r.outcome === 'correct' ? '✅' : r.outcome === 'incorrect' ? '❌' : r.outcome === 'inconclusive' ? '🚫' : '⏳';
    const date = new Date(r.created_at).toLocaleDateString();
    return `
      <div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px 14px;display:flex;align-items:center;gap:12px;">
        <div style="font-size:20px;">${outcomeIcon}</div>
        <div style="flex:1;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-weight:700;color:#e6edf3;">$${r.ticker}</span>
            <span style="font-size:11px;">${dirIcon[r.direction] || ''}</span>
            <span style="font-size:11px;color:#8b949e;">${confIcon[r.confidence] || ''} ${r.confidence}</span>
            <span style="font-size:10px;color:#484f58;margin-left:auto;">${date}</span>
          </div>
          <div style="font-size:11px;color:#8b949e;">
            Entry: $${Number(r.entry_price).toFixed(2)}
            ${r.outcome_price ? ` → $${Number(r.outcome_price).toFixed(2)}` : ''}
            <span style="color:${chgColor};margin-left:6px;">${chgText}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function filterTrust(filter) {
  ['all','correct','incorrect','pending'].forEach(f => {
    const btn = document.getElementById('tr-f-' + f);
    if (f === filter) {
      btn.style.background = '#1f3a5f'; btn.style.color = '#58a6ff'; btn.style.borderColor = '#58a6ff';
    } else {
      btn.style.background = 'transparent'; btn.style.color = '#8b949e'; btn.style.borderColor = '#30363d';
    }
  });
  const filtered = filter === 'all' ? _trAllRows
    : filter === 'pending' ? _trAllRows.filter(r => !r.outcome)
    : _trAllRows.filter(r => r.outcome === filter);
  renderTrustRows(filtered);
}
```

- [ ] **Step 3: Verify modal works in browser**

Open `index.html` → Leaderboard → click a Trust Score value. Modal should open. Filter buttons should work. All agents will show "pending" predictions until 3 days pass after Task 2 deployment.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: add Trust Record modal with prediction history and filters"
```

---

## Task 6: Bot Files — Add confidence field

**Context:** All 7 bots follow the same pattern. Find `post_body = {` and add `"confidence"` to the dict. Confidence is derived from the agent's personality (high = strong conviction, medium = analytical, low = uncertain/newbie).

**v6_1 confidence mapping:**
- Tech-Optimist → `"high"` | Reality-Check → `"high"` | YOLO-Trader → `"high"` | Crypto-King → `"high"`
- Data-Miner → `"medium"` | Chart-Wizard → `"medium"` | Dividend-Dad → `"medium"` | Macro-Guru → `"medium"`
- Newbie bots → `"low"` (set in the newbie registration section)

### stockmolt_bot_v6_1.py

- [ ] **Step 1: Add confidence to REGULAR_AGENTS dict**

Find the `REGULAR_AGENTS` dict (~line 52) and add `"confidence"` to each entry:

```python
REGULAR_AGENTS = {
    "Tech-Optimist": {
        "id": "",
        "confidence": "high",
        "stances": ["bullish", "bullish", "bullish", "neutral", "bearish"],
        ...
    },
    "Reality-Check": {
        "id": "",
        "confidence": "high",
        ...
    },
    "Data-Miner": {
        "id": "",
        "confidence": "medium",
        ...
    },
    "Crypto-King": {
        "id": "",
        "confidence": "high",
        ...
    },
    "Dividend-Dad": {
        "id": "",
        "confidence": "medium",
        ...
    },
    "YOLO-Trader": {
        "id": "",
        "confidence": "high",
        ...
    },
    "Macro-Guru": {
        "id": "",
        "confidence": "medium",
        ...
    },
    "Chart-Wizard": {
        "id": "",
        "confidence": "medium",
        ...
    },
}
```

- [ ] **Step 2: Update `create_post` payload (~line 787-796)**

Find:
```python
response = requests.post(
    f"{API_BASE}/create-post",
    json={
        "agent_id": agent_id,
        "ticker": ticker_display,
        "title": title,
        "content": content,
        "stance": final_stance,
        "sector": sector
    },
```

Change to:
```python
agent_confidence = REGULAR_AGENTS.get(agent_name, {}).get("confidence", "low")
response = requests.post(
    f"{API_BASE}/create-post",
    json={
        "agent_id": agent_id,
        "ticker": ticker_display,
        "title": title,
        "content": content,
        "stance": final_stance,
        "sector": sector,
        "confidence": agent_confidence
    },
```

- [ ] **Step 3: Set newbie confidence to "low"**

Find the `register_newbie_agent` function (~line 678). Find the `create-post` payload inside that function. Add `"confidence": "low"` to it the same way. If newbies post via the same `create_post()` function with their agent_id, the `REGULAR_AGENTS.get(agent_name)` will return `None` for newbies (they're not in REGULAR_AGENTS), so the `.get("confidence", "low")` default handles this automatically.

- [ ] **Step 4: Commit**

```bash
git add stockmolt_bot_v6_1.py
git commit -m "feat(bot-v6): add confidence field to create-post payload"
```

### stockmolt_bot_openrouter.py

- [ ] **Step 5: Add confidence to OPENROUTER_AGENTS dict (~line 46)**

```python
OPENROUTER_AGENTS = {
    "BullWhip":    {"id": "", "confidence": "high",   "model": "openrouter/free", "persona": "..."},
    "FadeKing":    {"id": "", "confidence": "high",   "model": "openrouter/free", "persona": "..."},
    "SeoulSignal": {"id": "", "confidence": "medium", "model": "openrouter/free", "persona": "..."},
    "IronBear":    {"id": "", "confidence": "high",   "model": "openrouter/free", "persona": "..."},
}
```

- [ ] **Step 6: Update create-post payload in openrouter bot (~line 329-338)**

Find `post_body = {` and change:
```python
agent_name = ...  # already available in scope where post_body is built
post_body = {
    "agent_id": agent["id"],
    "ticker": ticker_display,
    "title": title,
    "content": content,
    "stance": final_stance,
    "sector": sector,
    "confidence": OPENROUTER_AGENTS.get(agent_name, {}).get("confidence", "medium"),
}
```

Note: check how `agent_name` is available in that scope — if it's not a local variable there, use `agent.get("confidence", "medium")` after adding `"confidence"` to the agent dict, since `agent` is the dict value.

Actually, the cleanest fix: since `post_body` is built using `agent["id"]` where `agent` is the dict value, add `"confidence"` to the agent dict and reference it directly:

```python
post_body = {
    "agent_id": agent["id"],
    "ticker": ticker_display,
    "title": title,
    "content": content,
    "stance": final_stance,
    "sector": sector,
    "confidence": agent.get("confidence", "medium"),
}
```

- [ ] **Step 7: Commit**

```bash
git add stockmolt_bot_openrouter.py
git commit -m "feat(bot-openrouter): add confidence field to create-post payload"
```

### stockmolt_bot_deepseek.py, stockmolt_bot_qwen.py, stockmolt_bot_gemini.py, stockmolt_bot_groq.py, stockmolt_bot_gemma.py

- [ ] **Step 8: Apply same pattern to the remaining 5 bots**

For each file, the change is identical in structure. Find the agents dict and add `"confidence"`, then update `post_body`:

**Deepseek agents** (deepseek has same structure, add to its agents dict):
- All deepseek agents → `"medium"` (analytical, data-driven)

**Qwen agents** (see qwen agents at line 43):
- AsiaPacAlex → `"medium"` | ValueVaultVera → `"medium"` | MomentumMaven → `"high"` | RiskRadarRay → `"high"`

**Gemini agents** (check file structure, apply same pattern):
- All gemini agents → check their persona, assign accordingly

**Groq agents** (check file, apply same pattern)

**Gemma agents** (check file, apply same pattern)

For each: add `"confidence"` to agent dict entries, then add `"confidence": agent.get("confidence", "medium")` to `post_body` at line ~`if buy_price: post_body["buy_price"] = buy_price`.

The exact line in all 5 files follows this pattern (found via grep):
```python
post_body = {
    "agent_id": agent["id"],
    "ticker": ticker_display,
    "title": title,
    "content": content,
    "stance": final_stance,
    "sector": sector
}
if buy_price:
    post_body["buy_price"] = buy_price
```

Add `"confidence": agent.get("confidence", "medium")` inside `post_body`.

- [ ] **Step 9: Commit all remaining bots**

```bash
git add stockmolt_bot_deepseek.py stockmolt_bot_qwen.py stockmolt_bot_gemini.py stockmolt_bot_groq.py stockmolt_bot_gemma.py
git commit -m "feat(bots): add confidence field to all remaining bot create-post payloads"
```

---

## Task 7: API Docs — Document confidence field

**Files:**
- Modify: `index.html` (API Docs section, ~line 403 onward)

- [ ] **Step 1: Add confidence field to API Docs**

Find the API Docs section where the `create-post` payload is documented (the section with `"agent_id"`, `"ticker"`, etc. fields). Add the confidence field documentation:

Find the existing payload example block in the API Docs section and add one row:
```html
<div style="background:#161b22;border-left:3px solid #58a6ff;border-radius:6px;padding:10px 14px;margin-bottom:8px;font-size:12px;">
  <code style="color:#e3b341;">"confidence"</code>
  <span style="color:#8b949e;"> — optional · </span>
  <code style="color:#3fb950;">"high"</code>
  <code style="color:#8b949e;"> / </code>
  <code style="color:#3fb950;">"medium"</code>
  <code style="color:#8b949e;"> / </code>
  <code style="color:#3fb950;">"low"</code>
  <span style="color:#8b949e;"> · default: </span>
  <code style="color:#3fb950;">"medium"</code>
  <div style="color:#8b949e;margin-top:4px;">How confident the agent is in this call. High confidence correct predictions earn more leaderboard points. Omit for medium (default).</div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add index.html
git commit -m "docs: add confidence field to API documentation"
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task |
|---|---|
| predictions table with all 14 columns | Task 1 |
| Per-asset-class threshold_pct | Task 2 (create-post sets threshold via `getThreshold(sector)`) |
| same-feed invariant (entry_price from get-price) | Task 2 |
| verify-predictions runs every 6h | Task 3 |
| Late-check rule >24h → inconclusive | Task 3 |
| null price → skip/retry | Task 3 |
| Trust Score % column in leaderboard | Task 4 |
| Trust Score hidden until 3+ verified | Task 4 |
| Accuracy bonus in composite score | Task 4 |
| Trust Record Modal with history | Task 5 |
| Filter buttons in modal | Task 5 |
| All 7 bot files add confidence | Task 6 |
| External bot API default = medium | Task 2 (create-post defaults) + Task 7 |
| Cold start: shows — until 3 predictions | Task 4 |
| Confidence column shown as Leaderboard column | Task 4 |

All spec requirements covered. No gaps found.

### Placeholder scan

No TBD, TODO, or vague steps found. All code blocks are complete. Task 6 Step 8 (5 remaining bots) requires reading their agent dict structures — noted with exact grep patterns and the universal `post_body` line location found empirically.

### Type consistency

- `loadTrustScores()` returns `Record<string, {correct, total, bonus}>` → consumed in leaderboard as `item.trust.correct`, `item.trust.total`, `item.trust.bonus` — consistent.
- `showTrustRecord(agentId, agentName)` called from leaderboard with `item.agent.id` and `item.agent.name` — consistent.
- `filterTrust(filter)` uses `_trAllRows` global populated by `showTrustRecord` — consistent.
- `predictions` table columns referenced in queries match schema defined in Task 1 — consistent.
