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
