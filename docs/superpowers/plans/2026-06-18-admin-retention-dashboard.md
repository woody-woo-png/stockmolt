# Admin Retention Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** An auth-gated read-only retention dashboard: one `admin-stats` edge function (service-role, `ADMIN_TOKEN` header) that aggregates `players` + `game_daily_result` in TypeScript, plus a static `admin.html` shell that renders it.

**Architecture:** No DB migration, no cron. The function fetches the (tiny) raw rows and computes totals, a 14-day new/active series, cohort counts, streak distribution, a per-user table + 14-day activity grid, and a season snapshot (via the existing `get_season_leaderboard` RPC). The page holds no data — it prompts for the admin token, stores it in `localStorage`, and sends it as `x-admin-token`.

**Tech Stack:** Deno edge function (TypeScript), vanilla HTML/JS, Cloudflare Pages, Supabase.

**Spec:** `docs/superpowers/specs/2026-06-18-admin-retention-dashboard-design.md`

---

## Branch & deploy reality

- `admin-stats` (backend) → branch `feat/game-mvp-backend`. `admin.html` (frontend) → `main` (live via Cloudflare).
- Two isolated worktrees; commit nothing to `main` directly.
- **Two APPROVAL GATES:** ① set `ADMIN_TOKEN` secret + deploy `admin-stats` (owner supplies the token); ② push `admin.html`.
- Public constants (already public in `index.html`): functions base `https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1`, anon key `sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0`. The anon key is the Supabase gateway key (not the security boundary); `ADMIN_TOKEN` is.

## Setup: worktrees

- [ ] **Step 1:** `git -C c:\Users\amire\AI\stockmolt worktree add "c:\Users\amire\AI\stockmolt-wt-backend" feat/game-mvp-backend`
- [ ] **Step 2:** `git -C c:\Users\amire\AI\stockmolt worktree add -b feat/admin-dashboard "c:\Users\amire\AI\stockmolt-wt-frontend" main`

---

## Task 1: `admin-stats` edge function

**Files:** Create `supabase/functions/admin-stats/index.ts` (backend worktree)

- [ ] **Step 1: Create the file** with:

```ts
// supabase/functions/admin-stats/index.ts
// Auth-gated (x-admin-token == ADMIN_TOKEN) read-only retention aggregates. Service-role.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-admin-token",
};

const dayStr = (d: Date) => d.toISOString().slice(0, 10);
const todayUtc = () => dayStr(new Date());
const nDaysAgo = (n: number) => { const d = new Date(); d.setUTCDate(d.getUTCDate() - n); return dayStr(d); };

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  const token = req.headers.get("x-admin-token");
  const expected = Deno.env.get("ADMIN_TOKEN");
  if (!expected || token !== expected) {
    return new Response(JSON.stringify({ success: false, error: "unauthorized" }),
      { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }

  try {
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const today = todayUtc();
    const since = nDaysAgo(30);

    const { data: playersData } = await supabase.from("players")
      .select("id, device_id, display_name, level, xp, capital, streak_current, streak_best, last_played_date, created_at");
    const { data: resultsData } = await supabase.from("game_daily_result")
      .select("player_id, trade_date, beat_ai").gte("trade_date", since);

    const P = playersData ?? [];
    const R = resultsData ?? [];

    type Agg = { days: Set<string>; rounds: number; beats: number };
    const byPlayer: Record<string, Agg> = {};
    for (const r of R) {
      const a = (byPlayer[r.player_id] ??= { days: new Set(), rounds: 0, beats: 0 });
      a.days.add(r.trade_date); a.rounds++; if (r.beat_ai) a.beats++;
    }
    const isNamed = (p: any) => p.display_name && p.display_name !== "Trader-" + String(p.device_id).slice(0, 6);

    const totals = {
      players: P.length,
      named: P.filter(isNamed).length,
      active_today: new Set(R.filter((r) => r.trade_date === today).map((r) => r.player_id)).size,
      with_streak: P.filter((p) => Number(p.streak_current) > 0).length,
    };

    const days14 = [];
    for (let i = 13; i >= 0; i--) {
      const d = nDaysAgo(i);
      days14.push({
        date: d,
        new_players: P.filter((p) => String(p.created_at).slice(0, 10) === d).length,
        active_players: new Set(R.filter((r) => r.trade_date === d).map((r) => r.player_id)).size,
      });
    }
    const gridDays = days14.map((d) => d.date);

    const playedIds = Object.keys(byPlayer);
    const cohort = {
      played: playedIds.length,
      returning: playedIds.filter((id) => byPlayer[id].days.size >= 2).length,
      one_and_done: playedIds.filter((id) => byPlayer[id].days.size === 1).length,
      active_7d: new Set(R.filter((r) => r.trade_date >= nDaysAgo(6)).map((r) => r.player_id)).size,
    };

    const bucket = (s: number) => s >= 14 ? "14+" : s >= 7 ? "7-13" : s >= 3 ? "3-6" : s >= 1 ? "1-2" : "0";
    const streakDist: Record<string, number> = { "0": 0, "1-2": 0, "3-6": 0, "7-13": 0, "14+": 0 };
    for (const p of P) streakDist[bucket(Number(p.streak_current))]++;

    const users = P.map((p) => {
      const a = byPlayer[p.id] || { days: new Set<string>(), rounds: 0, beats: 0 };
      return {
        name: p.display_name || ("Trader-" + String(p.device_id).slice(0, 6)),
        created: String(p.created_at).slice(0, 10),
        last_active: p.last_played_date || null,
        active_days: a.days.size,
        streak: Number(p.streak_current), best: Number(p.streak_best),
        level: p.level, capital: Number(p.capital), rounds: a.rounds,
        beat_rate: a.rounds ? Math.round((a.beats / a.rounds) * 100) : 0,
        grid: gridDays.map((d) => (a.days.has(d) ? 1 : 0)),
      };
    }).sort((x, y) => (y.last_active || "").localeCompare(x.last_active || "") || y.rounds - x.rounds);

    let season: any = null;
    const { data: seas } = await supabase.from("game_seasons")
      .select("season_no, name, start_date, end_date").lte("start_date", today).gte("end_date", today).maybeSingle();
    if (seas) {
      const { data: lb } = await supabase.rpc("get_season_leaderboard",
        { p_start: seas.start_date, p_end: seas.end_date, p_limit: 10 });
      season = { name: seas.name, top: (lb ?? []).map((r: any) => ({ name: r.display_name, level: r.level, season_xp: Number(r.season_xp) })) };
    }

    return new Response(JSON.stringify({
      success: true, generated_at: new Date().toISOString(),
      totals, days14, grid_days: gridDays, cohort, streak_dist: streakDist, users, season,
    }), { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("admin-stats error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/functions/admin-stats/index.ts
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): admin-stats edge function (token-gated retention aggregates)"
```

---

## Task 2: `admin.html`

**Files:** Create `admin.html` at the repo root (frontend worktree)

- [ ] **Step 1: Create the file** with:

```html
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>StockMolt · Admin</title>
<style>
  :root{--bg:#0d1117;--card:#161b22;--line:#30363d;--mut:#8b949e;--txt:#f0f6fc;--vio:#7c3aed;--cy:#22d3ee;--gold:#e3b341;--grn:#3fb950;--red:#f85149;}
  *{box-sizing:border-box;font-family:system-ui,Segoe UI,Roboto,sans-serif;}
  body{margin:0;background:var(--bg);color:var(--txt);padding:18px;max-width:1100px;margin:0 auto;}
  h1{font-size:20px;margin:0 0 4px;} .sub{color:var(--mut);font-size:12px;margin-bottom:18px;}
  .row{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px;}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;min-width:130px;}
  .kpi .v{font-size:30px;font-weight:800;} .kpi .l{color:var(--mut);font-size:12px;margin-top:2px;}
  .box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:18px;}
  .box h2{font-size:14px;margin:0 0 12px;color:var(--cy);text-transform:uppercase;letter-spacing:1px;}
  table{width:100%;border-collapse:collapse;font-size:13px;} th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap;}
  th{color:var(--mut);font-weight:600;} .grid span{font-family:monospace;letter-spacing:1px;}
  .barwrap{display:flex;align-items:flex-end;gap:4px;height:70px;}
  .bar{flex:1;background:var(--vio);border-radius:3px 3px 0 0;min-height:2px;}
  .bar.a{background:var(--cy);} .barlabels{display:flex;gap:4px;font-size:9px;color:var(--mut);margin-top:4px;}
  .barlabels span{flex:1;text-align:center;}
  #login{max-width:320px;margin:80px auto;text-align:center;}
  input,button{font-size:15px;padding:10px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--txt);}
  button{background:var(--vio);border-color:var(--vio);font-weight:700;cursor:pointer;margin-top:10px;width:100%;}
  .err{color:var(--red);font-size:13px;margin-top:10px;} .pos{color:var(--grn);} .neg{color:var(--red);}
</style></head>
<body>
<div id="login">
  <h1>🔒 StockMolt Admin</h1>
  <div class="sub">Enter admin token</div>
  <input id="tok" type="password" placeholder="admin token" autocomplete="off" style="width:100%">
  <button onclick="saveTok()">Unlock</button>
  <div id="loginerr" class="err"></div>
</div>
<div id="app" style="display:none"></div>
<script>
const FN='https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1';
const ANON='sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0';
function tok(){return localStorage.getItem('sm_admin_token')||'';}
function saveTok(){const v=document.getElementById('tok').value.trim();if(!v)return;localStorage.setItem('sm_admin_token',v);load();}
function logout(){localStorage.removeItem('sm_admin_token');location.reload();}
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function money(n){return '$'+Math.round(Number(n)).toLocaleString();}

async function load(){
  try{
    const r=await fetch(FN+'/admin-stats',{headers:{'apikey':ANON,'Authorization':'Bearer '+ANON,'x-admin-token':tok()}});
    if(r.status===401){fail('Wrong token.');return;}
    const d=await r.json(); if(!d.success){fail('Error loading.');return;}
    document.getElementById('login').style.display='none';
    document.getElementById('app').style.display='block';
    render(d);
  }catch(e){fail('Network error.');}
}
function fail(m){
  const inLogin=document.getElementById('app').style.display!=='block';
  if(inLogin){document.getElementById('loginerr').textContent=m;}
  else{document.getElementById('app').innerHTML='<div class="err">'+esc(m)+'</div>';}
}

function bars(series,key,cls){
  const max=Math.max(1,...series.map(x=>x[key]));
  return '<div class="barwrap">'+series.map(x=>'<div class="bar '+cls+'" style="height:'+Math.round(x[key]/max*100)+'%" title="'+x.date+': '+x[key]+'"></div>').join('')+'</div>'
    +'<div class="barlabels">'+series.map(x=>'<span>'+x.date.slice(5)+'</span>').join('')+'</div>';
}

function render(d){
  const t=d.totals,c=d.cohort,sd=d.streak_dist;
  let h='';
  h+='<h1>📊 StockMolt Admin <button onclick="logout()" style="width:auto;float:right;background:var(--card);border-color:var(--line);font-size:12px;padding:6px 12px">Logout</button></h1>';
  h+='<div class="sub">Generated '+esc(d.generated_at)+' · counts (not rates) at founding scale</div>';
  h+='<div class="row">'
    +kpi(t.players,'Total players')+kpi(t.named,'Named')+kpi(t.active_today,'Active today')+kpi(t.with_streak,'Live streaks')
    +kpi(c.returning,'Returning (≥2 days)')+kpi(c.one_and_done,'One-and-done')+kpi(c.active_7d,'Active 7d')+'</div>';
  h+='<div class="box"><h2>New players · last 14 days</h2>'+bars(d.days14,'new_players','')+'</div>';
  h+='<div class="box"><h2>Active players · last 14 days</h2>'+bars(d.days14,'active_players','a')+'</div>';
  // streak dist
  h+='<div class="box"><h2>Streak distribution</h2><div class="row">'+Object.keys(sd).map(k=>kpi(sd[k],'streak '+k)).join('')+'</div></div>';
  // per-user + grid
  h+='<div class="box"><h2>Players</h2><table><thead><tr><th>name</th><th>created</th><th>last</th><th>days</th><th>streak</th><th>lvl</th><th>capital</th><th>rounds</th><th>beat AI</th><th>14d</th></tr></thead><tbody>';
  h+=d.users.map(u=>{
    const grid=u.grid.map(g=>g?'<span style="color:var(--grn)">●</span>':'<span style="color:var(--line)">·</span>').join('');
    const cap=Number(u.capital), capCls=cap>=100000?'pos':'neg';
    return '<tr><td>'+esc(u.name)+'</td><td>'+esc(u.created)+'</td><td>'+esc(u.last_active||'—')+'</td><td>'+u.active_days+'</td><td>'+u.streak+'/'+u.best+'</td><td>'+u.level+'</td><td class="'+capCls+'">'+money(u.capital)+'</td><td>'+u.rounds+'</td><td>'+u.beat_rate+'%</td><td class="grid">'+grid+'</td></tr>';
  }).join('')+'</tbody></table></div>';
  // season
  if(d.season){
    h+='<div class="box"><h2>🏆 '+esc(d.season.name)+' — top season XP</h2><table><thead><tr><th>#</th><th>name</th><th>lvl</th><th>season XP</th></tr></thead><tbody>'
      +d.season.top.map((s,i)=>'<tr><td>'+(i+1)+'</td><td>'+esc(s.name)+'</td><td>'+s.level+'</td><td>'+s.season_xp+'</td></tr>').join('')
      +(d.season.top.length?'':'<tr><td colspan="4" style="color:var(--mut)">no season XP yet</td></tr>')+'</tbody></table></div>';
  }
  document.getElementById('app').innerHTML=h;
}
function kpi(v,l){return '<div class="kpi"><div class="v">'+v+'</div><div class="l">'+esc(l)+'</div></div>';}

if(tok()) load();
</script>
</body></html>
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-frontend" add admin.html
git -C "c:\Users\amire\AI\stockmolt-wt-frontend" commit -m "feat(admin): token-gated retention dashboard page"
```

---

## Task 3: Set secret + deploy `admin-stats` — APPROVAL GATE

- [ ] **Step 1:** Get 지크님's approval; he chooses the admin token value.
- [ ] **Step 2: Set the secret** (owner runs, or supplies the value):
```
supabase secrets set ADMIN_TOKEN=<owner-chosen-strong-token> --project-ref oyatbvqpilvbhqpiafwp
```
- [ ] **Step 3: Deploy** (from the backend worktree, PATH refreshed):
```
supabase functions deploy admin-stats --project-ref oyatbvqpilvbhqpiafwp
```
- [ ] **Step 4: Smoke — 401 path (no token needed).**
```
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/admin-stats" -H "apikey: sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0"
```
Expected: `401` (no `x-admin-token`). With the correct token header it returns `200` + JSON — the full success path is verified by 지크님 in `admin.html` (Task 4), since only he has the token.

---

## Task 4: Push `admin.html` — APPROVAL GATE

- [ ] **Step 1:** `git -C c:\Users\amire\AI\stockmolt merge --ff-only feat/admin-dashboard`
- [ ] **Step 2 (REQUIRES approval):** `git -C c:\Users\amire\AI\stockmolt push origin main`
- [ ] **Step 3: Verify live (지크님).** Open `https://stockmolt.pages.dev/admin.html`, enter the admin token, confirm the dashboard loads (KPIs, 14-day bars, per-user table + grid, season). Clear the token (Logout) → returns to the locked prompt.
- [ ] **Step 4: Cleanup.**
```
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-backend"
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-frontend"
git -C c:\Users\amire\AI\stockmolt branch -d feat/admin-dashboard
git -C c:\Users\amire\AI\stockmolt push origin feat/game-mvp-backend   # backup the backend commit
```

---

## Self-Review notes

- **Spec coverage:** token auth (401 without) → Task 1 auth block + Task 3 smoke. TS aggregation, no migration → Task 1. Metrics (totals, 14-day new/active, cohort counts, streak dist, per-user table + 14-day grid, season snapshot) → Task 1 response + Task 2 render. Static shell, no embedded data → Task 2 (data only via fetch+token). CORS `x-admin-token` → Task 1 corsHeaders. ✓
- **Placeholder scan:** none — full function + page code; the only owner-supplied value is the token (by design). ✓
- **Type/name consistency:** response fields (`totals, days14, grid_days, cohort, streak_dist, users, season`) produced in Task 1 and consumed in Task 2 `render()`. `users[].grid` aligns with `grid_days`/`days14`. `get_season_leaderboard` params match its Phase 2a signature. ✓
- **Security:** data requires `ADMIN_TOKEN`; page ships no data; 401 short-circuits before any DB read; `noindex` meta; token only in owner's localStorage + function secret. ✓
- **Scale caveat:** active-days computed from last-30-day `game_daily_result` (fine at founding; the 14-day views need ≤14d anyway). Noted in spec.
